"""Offline demonstration around selected, unchanged production Store methods."""
import copy
import json
import tempfile
from pathlib import Path

from core import Batch, days, event, money
from ledger import Store

START, END = "2026-09-01", "2026-09-07"
HERE = Path(__file__).resolve().parent


def fixtures():
    cafe = {"kind": "order", "id": "demo-cafe-1", "events": [
        event("demo-payment", "demo-cafe-1", START + "T12:00:00+09:00", "payment", "120000"),
        event("demo-refund", "demo-cafe-1", "2026-09-04T10:00:00+09:00", "refund", "30000")]}
    smart = {"kind": "order", "id": "demo-smart-1", "events": [
        event("demo-smart-payment", "demo-smart-1", "2026-09-02T13:00:00+09:00", "payment", "80000")]}
    return [Batch(platform, "demo-account", START, END, [record], ["gross", "refunds"], mode="demo")
            for platform, record in [("cafe24", cafe), ("smartstore", smart)]]


def snapshot(store):
    """Read the actual demo DB; this presentation adapter is separate from production reports."""
    records = [json.loads(row[0]) for row in store.db.execute("SELECT payload FROM records")]
    result = []
    for day in days(START, "2026-09-08"):
        coverage = list(store.db.execute("SELECT complete_metrics FROM coverage WHERE day=?", (day,)))
        complete = bool(coverage) and all({"gross", "refunds"} <= set(json.loads(row[0])) for row in coverage)
        values = {metric: None for metric in ("gross", "refunds")}
        if complete:
            for metric, kind in [("gross", "payment"), ("refunds", "refund")]:
                values[metric] = str(sum((money(e["amount"]) for r in records for e in r["events"]
                                         if e["date"] == day and e["kind"] == kind), money(0)))
        result.append({"date": day, **values, "status": "ready" if complete else "not_collected"})
    return {"records": len(records), "rows": result,
            "gross": str(sum((money(r["gross"]) for r in result if r["gross"] is not None), money(0))),
            "refunds": str(sum((money(r["refunds"]) for r in result if r["refunds"] is not None), money(0)))}


def build_result():
    with tempfile.TemporaryDirectory(prefix="commerce-demo-") as folder:
        store = Store(Path(folder) / "demo.sqlite")
        try:
            batches = fixtures()
            for batch in batches:
                store.save("demo-brand", batch)
            first = snapshot(store)
            for batch in batches:
                store.save("demo-brand", batch)
            repeated = snapshot(store)
            corrected = copy.deepcopy(batches[0])
            corrected.records[0]["events"][1]["amount"] = "40000"
            store.save("demo-brand", corrected)
            refreshed = snapshot(store)
            plan = [{"date": row["date"], "metric": metric, "value": row[metric],
                     "action": "candidate" if row[metric] is not None else "hold"}
                    for row in refreshed["rows"] for metric in ("gross", "refunds")]
            return {"dataMode": "synthetic", "source": "unchanged production Store.save",
                    "first": first, "repeated": repeated, "refreshed": refreshed,
                    "duplicateStable": first == repeated, "plan": plan,
                    "notice": "Offline presentation example. No API calls or Google Sheets writes."}
        finally:
            store.close()


def render(result):
    number = lambda value: "—" if value is None else format(int(value), ",")
    rows = "".join(f'<tr><td>{r["date"]}</td><td class="num">{number(r["gross"])}</td>'
                   f'<td class="num">{number(r["refunds"])}</td><td><span class="tag {r["status"]}">'
                   f'{"입력 후보" if r["status"] == "ready" else "미수집 · 보류"}</span></td></tr>'
                   for r in result["refreshed"]["rows"])
    stages = "".join(f'<tr><td>{label}</td><td class="num">{result[key]["records"]}</td>'
                     f'<td class="num">{number(result[key]["gross"])}</td>'
                     f'<td class="num">{number(result[key]["refunds"])}</td></tr>'
                     for key, label in [("first", "첫 수집"), ("repeated", "같은 자료 재수집"), ("refreshed", "환불 원천 수정 후 재수집")])
    plan = "".join(f'<tr><td>{r["date"]}</td><td>{r["metric"]}</td>'
                   f'<td class="num">{number(r["value"])}</td><td>{"입력 후보" if r["action"] == "candidate" else "보류"}</td></tr>'
                   for r in result["plan"])
    stable = "PASS" if result["duplicateStable"] else "FAIL"
    document = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commerce Metrics · 실행 예제</title><style>
*{box-sizing:border-box}body{margin:0;background:#f4f3ef;color:#172b26;font:16px -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif}main{max-width:1120px;margin:36px auto;padding:0 24px}header{display:flex;justify-content:space-between;align-items:center}h1{font-size:30px;margin:6px 0 12px}p{color:#59675f;line-height:1.6}.badge,.tag{padding:6px 10px;border-radius:6px;font-size:13px;background:#e9eee8}.badge{background:#244b3b;color:white}nav{display:flex;gap:8px;margin:26px 0}button{padding:12px 22px;border:1px solid #d2dad3;border-radius:9px;background:white;color:#244b3b;font-size:15px;cursor:pointer}button.active{background:#244b3b;color:white}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:20px 0}.card,.panel{background:white;border:1px solid #d5dcd5;border-radius:12px;padding:22px}.value{font-size:28px;font-weight:700;margin-top:10px}.muted{font-size:14px;color:#617168}.panel{padding:8px 22px 18px}table{width:100%;border-collapse:collapse;font-size:15px}td,th{padding:12px 8px;border-bottom:1px solid #e5e9e5;text-align:left}th{color:#617168;font-weight:500}.num{text-align:right;font-variant-numeric:tabular-nums}.not_collected{background:#fff0d7;color:#805a13}.ready{color:#2f6246}section[hidden]{display:none}footer{margin:20px 0;color:#637168;font-size:14px}h2{font-size:21px}code{background:#edf1ed;padding:2px 5px;border-radius:4px}
</style><main><header><div><div class="muted">Commerce Metrics · 公開実行例</div><h1>수집한 숫자가 보고서로 가기 전</h1></div><span class="badge">가상 데이터 · 외부 쓰기 없음</span></header><p>실제 저장 로직으로 처리한 결과를 보여준다. 이 화면은 공개 예제용이며 운영 대시보드 캡처가 아니다.</p><nav><button class="active" onclick="show('daily',this)">일별 결과</button><button onclick="show('repeat',this)">재수집 검증</button><button onclick="show('plan',this)">입력 후보 · 보류</button></nav>
<section id="daily"><div class="cards"><div class="card"><div class="muted">결제 합계</div><div class="value">__GROSS__원</div></div><div class="card"><div class="muted">환불 합계 · 원천 수정 반영</div><div class="value">__REFUNDS__원</div></div><div class="card"><div class="muted">미수집 날짜</div><div class="value">__DAYS_HELD__일 · 보류</div></div></div><div class="panel"><h2>결제와 환불은 따로 기록한다</h2><table><thead><tr><th>날짜</th><th class="num">결제</th><th class="num">환불</th><th>상태</th></tr></thead><tbody>__ROWS__</tbody></table></div></section>
<section id="repeat" hidden><div class="cards"><div class="card"><div class="muted">같은 자료 재수집</div><div class="value">__STABLE__ · 합계 동일</div></div><div class="card"><div class="muted">저장된 원천 레코드</div><div class="value">__RECORDS__개 유지</div></div><div class="card"><div class="muted">나중에 바뀐 환불</div><div class="value">__FIRST_REFUND__ → __REFUNDS__</div></div></div><div class="panel"><h2>다시 가져와도 숫자가 불어나지 않는다</h2><table><thead><tr><th>실행 단계</th><th class="num">레코드 수</th><th class="num">결제 합계</th><th class="num">환불 합계</th></tr></thead><tbody>__STAGES__</tbody></table><p><code>Store.save</code>가 같은 원천 키를 갱신한다. 입력값을 수정한 뒤에는 새 값으로 교체한다.</p></div></section>
<section id="plan" hidden><div class="cards"><div class="card"><div class="muted">확인한 기간의 숫자</div><div class="value">__CANDIDATES__개 입력 후보</div></div><div class="card"><div class="muted">미수집 기간의 숫자</div><div class="value">__HELD__개 보류</div></div><div class="card"><div class="muted">실제 시트 입력</div><div class="value">0회 · 로컬 확인</div></div></div><div class="panel"><h2>미확인 값은 0으로 만들지 않는다</h2><table><thead><tr><th>날짜</th><th>지표</th><th class="num">값</th><th>처리</th></tr></thead><tbody>__PLAN__</tbody></table></div></section><footer>Python · SQLite / 입력 후보의 설명용 화면이며, 운영 시트의 대상·범위 검증과 입력 경로는 이 예제에 포함하지 않았다.</footer></main><script>function show(id,button){document.querySelectorAll('section').forEach(s=>s.hidden=s.id!==id);document.querySelectorAll('button').forEach(b=>b.classList.remove('active'));button.classList.add('active')}</script></html>'''
    document = document.replace("公開実行例", "공개 실행 예제")
    values = {"__ROWS__": rows, "__STAGES__": stages, "__PLAN__": plan, "__STABLE__": stable,
              "__GROSS__": number(result["refreshed"]["gross"]), "__REFUNDS__": number(result["refreshed"]["refunds"]),
              "__FIRST_REFUND__": number(result["first"]["refunds"]), "__RECORDS__": str(result["refreshed"]["records"]),
              "__DAYS_HELD__": str(sum(r["status"] != "ready" for r in result["refreshed"]["rows"])),
              "__CANDIDATES__": str(sum(r["action"] == "candidate" for r in result["plan"])),
              "__HELD__": str(sum(r["action"] == "hold" for r in result["plan"]))}
    for key, value in values.items():
        document = document.replace(key, value)
    return document


if __name__ == "__main__":
    result = build_result()
    (HERE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (HERE / "report.html").write_text(render(result))
    print(json.dumps({"duplicateStable": result["duplicateStable"], "records": result["refreshed"]["records"],
                      "gross": result["refreshed"]["gross"], "refunds": result["refreshed"]["refunds"],
                      "inputCandidates": sum(p["action"] == "candidate" for p in result["plan"]),
                      "held": sum(p["action"] == "hold" for p in result["plan"])}, ensure_ascii=False))
