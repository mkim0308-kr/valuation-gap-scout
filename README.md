# valuation-gap-scout

빅테크 & 반도체 오토-리서치 파이프라인 — DCF 적정가와 시장가 사이의
밸류에이션 괴리율을 정찰(scout)합니다.

> ⚠️ **투자 자문이 아닙니다.** 이 프로젝트는 공개 데이터(SEC EDGAR, Yahoo
> Finance)를 이용해 DCF 모델과 시장가 사이의 **밸류에이션 괴리율**을 계산하고,
> Claude로 그 맥락을 요약하는 리서치 도구입니다. 어떤 에이전트도 매수/매도
> 추천을 하지 않도록 지시되어 있지만, 출력은 어디까지나 참고용 정보이며
> 투자 판단과 책임은 사용자 본인에게 있습니다.

## 구조

4단계 에이전트 파이프라인이며, **Agent 1만 파이썬 코드**이고 나머지는 **Claude
Code 서브에이전트**입니다. API 키나 API 크레딧이 필요 없습니다 — Claude Code
자체(이 채팅)의 정액 요금 안에서 동작합니다.

```
python main.py TICKER
└── [Agent 1] quant/quant_agent.py      하드 데이터만 다룸 (LLM 없음)
      ├── quant/sec_data.py             SEC EDGAR XBRL: 10년 영업현금흐름/CapEx
      ├── quant/market_data.py          yfinance: 국채금리, 베타, 시가총액, 부채
      └── quant/dcf.py                  동적 WACC 계산 + 5년 DCF 적정주가
      -> data/{TICKER}_quant.json 저장

Claude Code 채팅에서 이어서 요청
├── [Agent 2] .claude/agents/tech-moat-auditor.md   기술/해자 감사
├── [Agent 3] .claude/agents/macro-risk-analyst.md  매크로/리스크 분석
└── [Agent 4] .claude/agents/cfo-report-writer.md   CFO 리포트 (Markdown)
      -> reports/{TICKER}_report.md 저장

data/      Agent 1이 저장하는 원본 JSON + Agent 2/3의 중간 JSON
reports/   Agent 4가 저장하는 최종 마크다운 리포트
tests/     dcf.py 단위 테스트
```

Agent 2, 3은 검색 없이 실행하면 근거가 부족한 항목을 `insufficient_data`로
표시하도록 지시되어 있습니다 — 모르는 걸 지어내지 않기 위함입니다. CFO
리포트(Agent 4)는 항상 투자 자문 아님 고지문을 포함하고, 매수/매도 같은 행동
지시 문구를 쓰지 않도록 제약되어 있습니다.

## 설치

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

이게 전부입니다 — Agent 1(퀀트)은 SEC EDGAR와 Yahoo Finance 공개 API만
사용하고, Agent 2~4는 이 Claude Code 세션 자체가 처리하므로 별도 API 키나
결제 설정이 필요 없습니다.

## 실행

**1단계 — 데이터 수집 + DCF 계산 (터미널)**

```bash
python main.py AAPL
```

`data/AAPL_quant.json`이 생성되고, SEC 10년 FCF·WACC·DCF 적정가·밸류에이션
괴리율이 콘솔에 출력됩니다.

**2단계 — 해석 리포트 생성 (Claude Code 채팅)**

이 채팅(또는 아무 Claude Code 세션)에서 이렇게 요청하세요:

> "AAPL 분석 리포트 만들어줘"

`tech-moat-auditor` → `macro-risk-analyst` → `cfo-report-writer` 서브에이전트가
순서대로 실행되어 `data/AAPL_tech_moat.json`, `data/AAPL_macro_risk.json`,
최종 `reports/AAPL_report.md`를 생성합니다.

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
