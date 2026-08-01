# valuation-gap-scout

빅테크 & 반도체 오토-리서치 파이프라인 — DCF 적정가와 시장가 사이의
밸류에이션 괴리율을 정찰(scout)합니다.

> ⚠️ **투자 자문이 아닙니다.** 이 프로젝트는 공개 데이터(SEC EDGAR, Yahoo
> Finance)를 이용해 DCF 모델과 시장가 사이의 **밸류에이션 괴리율**을 계산하고,
> Claude로 그 맥락을 요약하는 리서치 도구입니다. 어떤 에이전트도 매수/매도
> 추천을 하지 않도록 지시되어 있지만, 출력은 어디까지나 참고용 정보이며
> 투자 판단과 책임은 사용자 본인에게 있습니다.

## 구조

**Agent 1만 파이썬 코드**(결정론적 계산)이고 나머지는 **Claude Code
서브에이전트**(해석)입니다. API 키나 API 크레딧이 필요 없습니다 — Claude
Code 자체(이 채팅)의 정액 요금 안에서 동작합니다.

```
python main.py TICKER
└── [Agent 1] quant/quant_agent.py      하드 데이터만 다룸 (LLM 없음)
      ├── quant/sec_data.py             SEC EDGAR XBRL: 10년 영업현금흐름/CapEx
      ├── quant/market_data.py          yfinance: 국채금리, 베타, 시가총액, 부채
      ├── quant/dcf.py                  동적 WACC 계산 + 5년 DCF 적정주가
      └── quant/relative_valuation.py   Graham Number, PEG, ROE, ROIC, PSR, comps 배수, 오너어닝스
      -> data/{TICKER}_quant.json 저장 (relative_valuation 필드 포함)

python extended_metrics.py TICKER [--peers ...]   (선택, LLM 없음, 11개 모듈)
├── quant/peer_comps.py             피어 그룹 대비 배수/ROE 비교
├── quant/earnings_quality.py       Sloan 발생액 비율 + Beneish M-Score
├── quant/insider_institutional.py  내부자 매매 요약 + 기관/내부자 보유 비중
├── quant/historical_valuation.py   5년/52주 가격 밴드 내 퍼센타일
├── quant/options_market_signal.py  ATM 내재변동성 + 풋/콜 비율
├── quant/balance_sheet_health.py   Altman Z-Score, 이자보상배율, 유동비율, Debt/EBITDA
├── quant/capital_allocation.py     10년 CapEx/R&D/자사주매입/배당/M&A 비중
├── quant/shareholder_yield.py      배당+자사주매입 = 총주주환원율, 배당 CAGR
├── quant/short_interest.py         공매도 비율, Days to Cover, 전월 대비 변화
├── quant/analyst_estimates.py      애널리스트 목표가·추천등급 분포 (제3자 의견 인용)
└── quant/volatility_comparison.py  실현변동성 vs 옵션 내재변동성
      -> data/{TICKER}_extended_metrics.json 저장

Claude Code 채팅에서 이어서 요청
├── [Agent 2] .claude/agents/tech-moat-auditor.md          비즈니스 해자 감사 (업종에 맞는 유형만 선택 — 아래 참고)
├── [Agent 3] .claude/agents/macro-risk-analyst.md         매크로/리스크 분석
├── [Agent 4] .claude/agents/guru-perspective-analyst.md   Graham/Buffett/Lynch/Marks/Ken Fisher/Greenblatt 6인의 공개 기준 적용
├── [Agent 6] .claude/agents/litigation-regulatory-agent.md 진행 중인 소송·규제 조사 검색 (선택)
├── [Agent 7] .claude/agents/consensus-bull-bear-agent.md  시장 강세론·약세론 양쪽 검색·인용 (선택)
├── [Agent 8] .claude/agents/debate-synthesis-agent.md     위 모든 산출물을 교차 비교해 일치점/긴장점 종합 (2~7 이후, 5 이전)
└── [Agent 5] .claude/agents/cfo-report-writer.md          CFO 리포트 (Markdown, 맨 위에 종합 요약 배치)
      -> reports/{TICKER}_report.md 저장 (선택 입력 파일이 있으면 해당 섹션 추가)
      -> python render_html.py TICKER 실행 -> reports/{TICKER}_report.html 저장

data/      Agent 1/1b~1g·6·7·8이 저장하는 원본 JSON + Agent 2/3/4의 중간 JSON
reports/   Agent 5가 저장하는 마크다운 리포트 + render_html.py가 생성하는 HTML
tests/     단위 테스트 (quant/, render_html.py)
```

Agent 2, 3, 4, 6, 7은 검색 없이 실행하면 근거가 부족한 항목을
`insufficient_data`로 표시하도록 지시되어 있습니다 — 모르는 걸 지어내지
않기 위함입니다. **Agent 2(비즈니스 해자)**는 반도체 제조사 전용 체크리스트가
아니라 Morningstar의 5가지 경제적 해자 분류(네트워크 효과/전환비용/원가우위/
무형자산/효율적 규모)를 바탕으로, 먼저 회사의 업종·비즈니스 모델을 파악한 뒤
실제로 해당하는 유형만 골라 분석합니다. **Agent 4(구루 관점)**는 실제 인물의
의견이 아니라 **공개적으로 알려진 투자 방법론(공식/기준)을 데이터에
기계적으로 대입한 결과**라는 점을 항상 고지문에 명시하도록 제약되어
있습니다. Agent 6(소송·규제)은 승패를 예측하지 않고 사실관계만 서술합니다.
Agent 7(강세론·약세론)은 반드시 양쪽 주장을 함께 인용하고 종합 결론을
내리지 않습니다. **Agent 8(종합 판단)**은 다른 에이전트들이 서로 실시간
대화하지 않는다는 점을 전제로, 모든 산출물을 사후에 읽고 비교해 일치점·
긴장점·종합 서술을 만듭니다 — 진짜 "토론"이 아니라 사후 교차검증이라는
점을 리포트에도 명시합니다. CFO 리포트(Agent 5)는 항상 투자 자문 아님
고지문을 포함하고, 매수/매도 같은 행동 지시 문구를 쓰지 않도록 제약되어
있습니다.

## 설치

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

이게 전부입니다 — 파이썬 에이전트는 SEC EDGAR와 Yahoo Finance 공개 API만
사용하고, Claude Code 서브에이전트들은 이 세션 자체가 처리하므로 별도
API 키나 결제 설정이 필요 없습니다.

## 실행

**1단계 — 데이터 수집 + DCF 계산 (터미널)**

```bash
python main.py AAPL
```

`data/AAPL_quant.json`이 생성되고, SEC 10년 FCF·WACC·DCF 적정가·밸류에이션
괴리율이 콘솔에 출력됩니다.

**2단계 — 확장 지표 수집 (선택, 터미널)**

```bash
python extended_metrics.py AAPL --peers MSFT GOOGL NVDA
```

피어 비교, 이익의 질(Beneish M-Score 등), 내부자·기관 동향, 과거 가격 밴드
위치, 옵션 시장 신호, 재무 건전성(Altman Z-Score 등), 자본배치 이력,
주주환원율, 공매도 동향, 애널리스트 컨센서스, 실현/내재 변동성까지 11개
지표가 `data/AAPL_extended_metrics.json`에 저장됩니다. `--peers`를
생략하면 몇몇 빅테크/반도체 종목에 한해 기본 피어 그룹을 사용하고, 그 외
종목은 `insufficient_data`로 남습니다. 이 단계를 건너뛰어도 3단계는
정상 동작합니다 (해당 섹션만 리포트에서 빠집니다).

**3단계 — 해석 리포트 생성 (Claude Code 채팅)**

이 채팅(또는 아무 Claude Code 세션)에서 이렇게 요청하세요:

> "AAPL 분석 리포트 만들어줘"

`tech-moat-auditor` → `macro-risk-analyst` → `guru-perspective-analyst` →
(선택) `litigation-regulatory-agent` → (선택) `consensus-bull-bear-agent`
→ `debate-synthesis-agent` → `cfo-report-writer` 서브에이전트가 순서대로
실행되어 `data/AAPL_tech_moat.json`, `data/AAPL_macro_risk.json`,
`data/AAPL_guru_perspectives.json`, (선택)
`data/AAPL_litigation_regulatory.json`, (선택)
`data/AAPL_bull_bear_consensus.json`, `data/AAPL_executive_summary.json`,
`reports/AAPL_report.md`를 생성하고, 마지막에 `render_html.py`를 실행해
`reports/AAPL_report.html`까지 만듭니다. `executive_summary.json`은
나머지 에이전트 결과를 모두 교차 비교한 종합으로, 리포트 맨 위에
"종합 요약" 섹션으로 배치됩니다.

**4단계 — HTML만 다시 렌더링하고 싶을 때 (터미널)**

마크다운 리포트를 수정했거나 HTML만 다시 뽑고 싶으면:

```bash
python render_html.py AAPL
```

`reports/AAPL_report.html`을 브라우저로 열면 시스템 라이트/다크 모드에 맞춰
자동으로 배색이 바뀌는 깔끔한 리포트 페이지를 볼 수 있습니다 (서버·외부
CDN·자바스크립트 없이 동작하는 단일 HTML 파일).

## 테스트

```bash
pytest tests/
```

## 알려진 한계

- SEC EDGAR XBRL 태그는 기업마다 명명이 조금씩 달라, 일부 종목은 10년 전체
  FCF 데이터가 수집되지 않을 수 있습니다.
- WACC의 부채비용은 개별 회사채 수익률이 아니라 국채금리 + 고정 스프레드로
  근사한 값입니다.
- Agent 2/3은 서브에이전트에 WebSearch/WebFetch 도구가 있지만, 검색으로
  근거를 찾지 못하면 `insufficient_data`를 반환하도록 지시되어 있습니다.
- `relative_valuation`의 P/E·EV/EBITDA·P/B·EPS·장부가는 yfinance가 제공하지
  않으면 `None`으로 남습니다 (지어내지 않음). PEG 계산용 성장률도 yfinance의
  forward 추정치가 없으면 10년 FCF CAGR로 대체하며, 이 경우
  `growth_rate_source`에 대체 사용 사실이 표시됩니다.
- "구루 관점"(Agent 4)은 Graham/Buffett/Lynch/Marks/Ken Fisher/Greenblatt가
  저서·주주서한 등에서 **공개한 방법론을 기계적으로 계산에 대입**한 것으로,
  해당 인물의 실제 의견이나 이 회사에 대한 언급이 아닙니다. Ken Fisher의
  PSR 기준은 1980년대 산업재·경기순환주 대상으로 검증된 것이라, 자산
  경량화 플랫폼/서비스 기업에는 원래 설계 의도와 잘 맞지 않을 수 있습니다.
- **비즈니스 해자**(Agent 2)는 반도체 제조사 전용 체크리스트가 아니라
  업종에 맞는 해자 유형을 선택해 분석하도록 바뀌었습니다. 다만 업종
  판단 자체가 WebSearch 결과에 의존하므로, 잘못 분류될 경우 뒤따르는
  분석의 관련성이 떨어질 수 있습니다.
- **종합 요약**(Agent 8, debate-synthesis-agent)은 다른 에이전트들이
  실시간으로 서로 대화하며 만들어낸 결론이 아닙니다 — 이 프레임워크의
  서브에이전트는 각자 독립적으로 실행되고 결과만 반환하므로, "토론"은
  한 에이전트가 모든 결과물을 사후에 읽고 비교하는 방식으로 시뮬레이션한
  것입니다. 리포트 본문에도 이 사실이 명시됩니다.
- **피어 비교**: `quant/peer_comps.py`의 기본 피어 그룹은 이 프로젝트가
  다루는 빅테크·반도체 종목 십여 개만 커버하는 수작업 목록입니다. 목록에
  없는 티커는 `--peers`로 직접 지정해야 하며, 지정하지 않으면
  `insufficient_data`로 남습니다.
- **이익의 질**: Beneish M-Score는 8개 구성요소가 모두 계산 가능해야
  산출되며, yfinance 재무제표에 필요한 항목이 없으면 `None`입니다. 임계값을
  넘어도 회계 조작을 의미하지 않습니다 — 매출/자산이 빠르게 느는 고성장
  기업은 정상적으로도 지표가 높게 나오는 경향이 있는, 잘 알려진 오탐
  패턴입니다.
- **내부자 매매 요약**: yfinance에 신뢰할 수 있는 거래 유형 코드가 없어,
  SEC Form 4의 자유 텍스트 설명("Sale...", "Purchase...", "Stock Gift...")을
  키워드로 분류합니다. 옵션 행사·부여 등은 "other"로 분류되며 매수/매도
  판단에 포함되지 않습니다.
- **과거 밴드 내 위치**: 5년/52주 가격 퍼센타일이지, 과거 시점의 DCF
  밸류에이션 갭을 재계산한 것이 아닙니다 (과거 재무제표 전체를 다시
  가져와야 해서 범위 밖으로 뒀습니다). 순수하게 "지금 가격이 최근 가격
  범위 중 어디쯤인지"를 보여주는 지표입니다.
- **옵션 시장 신호**: 내재변동성·풋/콜 비율은 현재 옵션 시장의 포지셔닝
  스냅샷이며, 미래 방향을 예측하는 지표가 아닙니다. 만기 30일 근처 옵션
  체인 하나만 사용합니다.
- **재무 건전성(Altman Z-Score)**: 1968년 원 모델은 제조업 기준으로
  설계되어, 자산 경량화 기업(대형 기술주 등)은 시가총액/부채 비율이 커서
  구조적으로 높게 나오는 경향이 있습니다. 절대 수치보다 방향성 참고용입니다.
- **자본배치 이력**: CapEx·R&D·자사주매입·배당·M&A 각각의 SEC XBRL 태그가
  기업마다 보고 이력이 달라, 카테고리별 연도 범위가 서로 다를 수 있습니다
  (`years_covered`에 실제 커버 연도가 표시됩니다).
- **주주환원**: 자사주매입수익률은 가장 최근 회계연도의 SEC 보고 지출액을
  현재 시가총액으로 나눈 과거 기준 수치이며, 향후 지속을 보장하지 않습니다.
- **공매도 동향**: 거래소가 월 단위로 보고하는 수치라 최대 몇 주 지연될 수
  있습니다.
- **애널리스트 컨센서스**: 목표주가·추천등급은 애널리스트들이 실제로
  발표한 제3자 의견을 그대로 인용한 것이며, 이 파이프라인의 자체 판단이
  아닙니다.
- **실현 vs 내재 변동성**: 실현변동성은 최근 가격 이력 기반, 내재변동성은
  옵션 시장 가격 기반으로, 미래 변동성을 예측하는 지표가 아닙니다.
- **소송·규제 리스크 / 시장 강세론·약세론**(Agent 6, 7): WebSearch 결과에
  의존하므로 검색 시점에 따라 결과가 달라질 수 있고, 최신이거나 완전한
  정보를 보장하지 않습니다. 두 에이전트 모두 사실관계·인용 위주로만
  작성하도록 지시되어 있으며, 승패 예측이나 투자 결론을 내리지 않습니다.
