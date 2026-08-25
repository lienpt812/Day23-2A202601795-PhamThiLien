# Tai lieu giai thich trien khai du an

## 1. Muc tieu du an

Du an nay xay dung mot workflow LangGraph cho agent xu ly ticket ho tro khach hang.
Workflow can co cac kha nang chinh:

- Quan ly state co schema ro rang.
- Phan loai ticket bang LLM.
- Dieu huong theo route: simple, tool, missing_info, risky, error.
- Goi mock tool khi can lookup hoac thuc hien action.
- Co retry loop co gioi han.
- Co human-in-the-loop approval cho hanh dong rui ro.
- Co checkpointer de luu trang thai.
- Sinh metrics va report de nop bai.

## 2. Cac phan da hoan thien

### 2.1. `state.py`

File nay dinh nghia state dung chung cho toan bo graph.

Da bo sung cac field quan trong:

- `evaluation_result`: ket qua danh gia tool result, dung de quyet dinh retry hay answer.
- `pending_question`: cau hoi can hoi lai user khi ticket thieu thong tin.
- `proposed_action`: hanh dong rui ro can approval.
- `approval`: quyet dinh approve/reject cua reviewer.

Nguyen tac reducer:

- Cac field scalar nhu `route`, `risk_level`, `attempt`, `final_answer` duoc overwrite.
- Cac field list nhu `messages`, `tool_results`, `errors`, `events` dung reducer `add`, tuc la append-only.

Ly do:

- Append-only giup metrics va audit trail dem duoc node da di qua.
- Scalar overwrite giup state gon, tranh tich luy du lieu cu khong can thiet.

### 2.2. `routing.py`

File nay chua cac ham dieu huong cho conditional edges trong LangGraph.

Da implement:

- `route_after_classify`
- `route_after_evaluate`
- `route_after_retry`
- `route_after_approval`

Mapping chinh:

```text
simple       -> answer
tool         -> tool
missing_info -> clarify
risky        -> risky_action
error        -> retry
unknown      -> answer
```

Retry logic:

```text
evaluation_result == "needs_retry" -> retry
otherwise                          -> answer
```

Bounded retry:

```text
attempt < max_attempts  -> tool
attempt >= max_attempts -> dead_letter
```

Approval logic:

```text
approved == true  -> tool
approved == false -> clarify
```

### 2.3. `nodes.py`

File nay chua logic cua tung buoc trong workflow.

Da implement cac node:

- `intake_node`
- `classify_node`
- `tool_node`
- `evaluate_node`
- `answer_node`
- `ask_clarification_node`
- `risky_action_node`
- `approval_node`
- `retry_or_fallback_node`
- `dead_letter_node`
- `finalize_node`

#### `classify_node`

Dung LLM that thong qua `get_llm()`.

Dung structured output bang Pydantic model `ClassificationResult`.

LLM chi duoc chon mot trong cac route:

- `simple`
- `tool`
- `missing_info`
- `risky`
- `error`

Prompt co neu priority:

```text
risky > tool > missing_info > error > simple
```

Dieu nay rat quan trong vi hidden tests co the dua ticket moi, khong trung sample scenario.

#### `tool_node`

Day la mock tool.

Behavior:

- Neu route la `error` va `attempt < 2`, tra ve chuoi co `"ERROR"` de kich hoat retry.
- Neu route la `tool`, tra ve mock lookup result.
- Neu route la `risky`, thuc hien mock approved action.
- Cac truong hop khac tra ve mock success.

#### `evaluate_node`

Danh gia tool result moi nhat.

Hien tai dung heuristic:

```text
neu latest_result co "ERROR" -> evaluation_result = "needs_retry"
nguoc lai                  -> evaluation_result = "success"
```

Phan nay du cho base score. Neu muon bonus, co the nang cap thanh LLM-as-judge.

#### `answer_node`

Dung LLM that de sinh final answer.

Context dua vao LLM gom:

- query goc
- route
- tool_results
- approval
- proposed_action

Yeu cau LLM chi tra loi dua tren workflow context, khong tu bia account data.

#### `ask_clarification_node`

Dung khi ticket qua mo ho.

Vi du:

```text
Can you fix it?
```

Agent se hoi lai thong tin cu the thay vi hallucinate.

#### `risky_action_node`

Dung khi ticket co hanh dong side-effect nhu:

- refund
- delete account
- cancel subscription
- send confirmation email

Node nay tao `proposed_action` va dat `risk_level = "high"`.

#### `approval_node`

Mac dinh mock approval:

```text
approved = true
reviewer = mock-reviewer
```

Neu set:

```env
LANGGRAPH_INTERRUPT=true
```

node co the dung `langgraph.types.interrupt()` cho HITL that.

#### `retry_or_fallback_node`

Moi lan retry:

- tang `attempt`
- ghi error vao `errors`
- ghi event `retry`

Day la node quan trong de tranh unbounded loop.

#### `dead_letter_node`

Dung khi retry da vuot qua `max_attempts`.

Node nay set final answer giai thich request khong the hoan tat va can manual review.

#### `finalize_node`

Moi route phai di qua node nay truoc khi ket thuc.

Metrics se dua vao `events` de biet workflow da den finalize hay chua.

### 2.4. `graph.py`

File nay wire cac node thanh LangGraph workflow.

Flow hien tai:

```text
START
  -> intake
  -> classify
  -> conditional route_after_classify

simple:
  answer -> finalize -> END

tool:
  tool -> evaluate -> answer/retry

missing_info:
  clarify -> finalize -> END

risky:
  risky_action -> approval -> tool/clarify

error:
  retry -> tool/dead_letter

retry:
  retry -> tool neu attempt < max_attempts
  retry -> dead_letter neu attempt >= max_attempts
```

Tat ca path deu ket thuc tai:

```text
finalize -> END
```

## 3. Cach chay hien tai

Neu chua install package editable:

```powershell
pip install -e ".[dev]"
```

Neu dung Gemini:

```powershell
pip install -e ".[dev,google]"
```

Neu dung OpenAI:

```powershell
pip install -e ".[dev,openai]"
```

Neu dung Anthropic:

```powershell
pip install -e ".[dev,anthropic]"
```

Can cau hinh `.env`:

```env
GEMINI_API_KEY=...
# hoac OPENAI_API_KEY=...
# hoac ANTHROPIC_API_KEY=...
```

Trong PowerShell, neu test bi skip vi khong thay key, export bien moi truong:

```powershell
$env:GEMINI_API_KEY="your-key"
$env:PYTHONPATH="src"
pytest tests\test_graph_smoke.py -q
```

Chay test co ban:

```powershell
$env:PYTHONPATH="src"
pytest tests\test_state.py tests\test_routing.py -q
```

Chay full test:

```powershell
$env:PYTHONPATH="src"
pytest -q
```

## 4. Viec can lam tiep theo

### Buoc 1: Kiem tra graph end-to-end voi LLM key

Can chay:

```powershell
$env:PYTHONPATH="src"
$env:GEMINI_API_KEY="your-key"
pytest tests\test_graph_smoke.py -q
```

Neu pass, graph da chay duoc end-to-end.

Neu fail, thuong se nam o:

- Chua cai provider package, vi du `langchain-google-genai`.
- API key chua export vao shell.
- LLM classify sai mot sample route.

### Buoc 2: Chay scenarios

Lenh muc tieu:

```powershell
make run-scenarios
```

Tren Windows neu `make` khong kha dung, co the chay truc tiep:

```powershell
$env:PYTHONPATH="src"
python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json
```

Ket qua mong doi:

- Tao `outputs/metrics.json`
- Co metric cho 7 scenario sample
- `success_rate` cang gan 100% cang tot

### Buoc 3: Implement `report.py`

Hien tai day la phan nen lam tiep.

Can implement:

- `render_report(metrics: MetricsReport) -> str`
- Ghi summary metrics.
- Ghi bang ket qua tung scenario.
- Giai thich architecture.
- Giai thich failure modes.
- Neu improvement plan.

Sau khi implement, `run-scenarios` se tao:

```text
reports/lab_report.md
```

### Buoc 4: Validate metrics

Chay:

```powershell
make grade-local
```

Hoac:

```powershell
$env:PYTHONPATH="src"
python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json
```

Neu pass, file metrics hop schema grading.

### Buoc 5: Implement persistence SQLite

Hien tai `persistence.py` moi co `memory`.

Nen implement them:

```yaml
checkpointer: sqlite
```

Va `database_url`, vi du:

```yaml
database_url: outputs/checkpoints.sqlite
```

Implementation du kien:

- Dung `sqlite3.connect(database_url, check_same_thread=False)`.
- Bat WAL mode.
- Tao `SqliteSaver`.
- Tra checkpointer ve cho `build_graph`.

Can cai dependency:

```powershell
pip install -e ".[sqlite]"
```

Muc dich:

- Co checkpoint that.
- Chung minh resume/history.
- Tang diem persistence/extension.

## 5. Thu tu uu tien de hoan thien bai nop

Nen lam theo thu tu nay:

1. Chay smoke test voi API key that.
2. Sua neu LLM classify sai route sample.
3. Chay `run-scenarios`.
4. Implement `report.py`.
5. Chay `validate-metrics`.
6. Implement SQLite persistence.
7. Cap nhat report bang bang metrics va evidence persistence.
8. Chay lai full validation.

## 6. Cac loi thuong gap

### 6.1. Test graph bi skip

Ly do:

- Test file kiem tra `os.getenv(...)`.
- No khong tu doc `.env`.

Cach sua:

```powershell
$env:GEMINI_API_KEY="your-key"
```

Hoac dung OpenAI/Anthropic key tuong ung.

### 6.2. Loi import package

Neu gap:

```text
ModuleNotFoundError: No module named 'langgraph_agent_lab'
```

Cach sua nhanh:

```powershell
$env:PYTHONPATH="src"
```

Cach sua ben vung:

```powershell
pip install -e ".[dev]"
```

### 6.3. LLM classify sai route

Neu sample route sai, can chinh prompt trong `classify_node`.

Priority nen giu:

```text
risky > tool > missing_info > error > simple
```

Vi du:

- `Refund this customer...` phai la `risky`.
- `Delete customer account...` phai la `risky`.
- `Please lookup order status...` phai la `tool`.
- `Can you fix it?` phai la `missing_info`.
- `Timeout failure...` phai la `error`.

### 6.4. Retry loop khong dung

Can kiem tra:

- `retry_or_fallback_node` co tang `attempt`.
- `route_after_retry` co so sanh `attempt < max_attempts`.
- `tool_node` co tra `"ERROR"` cho error route khi attempt thap.
- `evaluate_node` co set `needs_retry` khi thay `"ERROR"`.

## 7. Cach giai thich khi demo

Co the noi ngan gon:

Du an dung LangGraph de tach workflow thanh cac node doc lap. State la TypedDict co reducer append-only cho audit fields. LLM dung de classify ticket va sinh answer. Conditional routing dieu huong ticket vao cac path khac nhau. Tool path co evaluate node de quyet dinh retry hay answer. Risky path bat buoc qua approval node truoc khi tool execution. Error path di qua retry loop co gioi han, neu vuot gioi han thi vao dead letter. Tat ca cac path deu qua finalize de tao audit event va metrics.

## 8. Checklist truoc khi nop

- [ ] `.env` co API key hop le.
- [ ] Provider package da cai.
- [ ] `pytest -q` pass hoac graph tests pass khi co key.
- [ ] `outputs/metrics.json` duoc tao.
- [ ] `validate-metrics` pass.
- [ ] `reports/lab_report.md` da co noi dung.
- [ ] Khong con `NotImplementedError` o cac file core.
- [ ] Co the giai thich route simple/tool/risky/error.
- [ ] Co the giai thich retry va dead-letter.
- [ ] Neu muon diem cao, co SQLite persistence evidence.

## 9. Nhat ky tien do

### 2026-08-25

- Da hoan thien `state.py`: bo sung field cho retry, clarification, risky action va approval.
- Da hoan thien `routing.py`: route sau classify, evaluate, retry va approval.
- Da hoan thien `nodes.py`: LLM classification, LLM answer, mock tool, evaluate, clarify, risky action, approval, retry, dead letter va finalize.
- Da hoan thien `graph.py`: wire day du LangGraph workflow va dam bao moi path di qua `finalize`.
- Da cai provider dependency cho Gemini bang `pip install -e ".[google]"` vi `.env` dang dung `GEMINI_API_KEY`.
- Da chay `tests/test_graph_smoke.py` voi network cho Gemini API: 6 smoke tests pass.
- Da them `configs/lab_no_report.yaml` de chay scenarios va sinh metrics ma khong goi `report.py`.
- Da thu chay `run-scenarios` voi `configs/lab_no_report.yaml`, nhung bi dung do Gemini free-tier quota het: `429 RESOURCE_EXHAUSTED`. Chua tao duoc `outputs/metrics.json`.
- Da cai `langgraph-checkpoint-sqlite` bang `pip install -e ".[sqlite]"`.
- Da hoan thien `persistence.py`: ho tro `memory`, `sqlite`, `none`; SQLite dung `SqliteSaver(conn=...)` va bat WAL mode.
- Da them `configs/lab_sqlite_no_report.yaml` de chay scenarios voi SQLite checkpoint ma khong goi `report.py`.
- Da verify SQLite checkpointer khoi tao duoc `SqliteSaver`; `ruff` cho `persistence.py` pass; state/routing tests van pass 16/16.
- Da cap nhat `.gitignore` de bo qua checkpoint SQLite artifacts trong `outputs/`.
