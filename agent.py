#!/usr/bin/env python3
"""
Fintech SEA Weekly Scan Agent
=============================

Quet tin tuc Fintech cong khai (Dong Nam A / Viet Nam) trong 7 ngay gan nhat va
tong hop thanh ban tin theo 4 truc phuc vu BD cua Zalopay:

  1. Xu huong Fintech Dong Nam A trong tuan
  2. Cap nhat san pham moi dang chu y
  3. Thi truong co chuyen dich gi
  4. Chinh sach / quy dinh moi ho tro cong viec BD

Khong bao gom thong tin rieng ve Zalopay.

Yeu cau: ANTHROPIC_API_KEY trong environment.

Hai che do chay:
  1. CLI (mac dinh khi co flag --output hoac --once):
       python agent.py --output report.md
  2. Web service (de deploy len GreenNode AgentBase):
       python agent.py --serve
     -> lang nghe port 8080 (hoac $PORT), expose:
          GET  /health  -> {"status": "ok"}
          POST /invoke  -> chay weekly scan va tra ve {"output": "<markdown>"}
"""

import argparse
import datetime
import os
import sys
from pathlib import Path

import anthropic

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
MAX_SEARCH_USES = 8

SYSTEM_PROMPT = """\
Ban la mot research analyst ho tro Business Development (BD) cua Zalopay.

Nhiem vu: quet tin tuc Fintech cong khai tren internet trong 7 ngay gan nhat va
tong hop thanh mot ban tin ngan, actionable, theo dung 4 truc sau (KHONG bao gom
thong tin rieng ve Zalopay):

1. Xu huong Fintech Dong Nam A trong tuan (AI, embedded finance, blockchain,
   ngan hang so, financial inclusion, thanh toan...)
2. Cap nhat san pham moi dang chu y (vi dien tu, QR, ngan hang so, BNPL,
   thanh toan xuyen bien gioi...) o Viet Nam va Dong Nam A
3. Thi truong co chuyen dich gi (tang truong, M&A, hop tac ngan hang - fintech,
   thay doi canh tranh giua cac vi dien tu)
4. Chinh sach / quy dinh moi ban hanh ho tro cong viec BD (sandbox, luat bao ve
   du lieu, quy dinh NHNN, giay phep trung gian thanh toan, stablecoin/crypto...)

Quy tac:
- Moi truc: 3-5 bullet, suc tich, di thang vao thong tin.
- Moi bullet kem nguon (link) ro rang.
- Sau moi truc, neu phu hop, them mot dong "Goi y cho BD:" - goc ap dung thuc te.
- Khong lap lai thong tin giua cac truc.
- KHONG dua thong tin ve Zalopay (san pham, doi tac, tin tuc rieng cua Zalopay).
- Cuoi ban tin: ghi ro ngay tong hop va pham vi thoi gian (7 ngay gan nhat tinh
  tu ngay chay).
- Van phong: tieng Viet, ngan gon, chuyen nghiep.
- Luon dung tu khoa tim kiem kem thang/nam hien tai de tranh ket qua loi thoi.
- Output dang Markdown, voi 4 heading ro rang cho 4 truc.
"""

USER_PROMPT_TEMPLATE = """\
Hom nay la {today}. Hay quet tin tuc Fintech (Dong Nam A va Viet Nam) trong 7 ngay
gan nhat (tu {week_ago} den {today}) va tong hop ban tin theo 4 truc da neu trong
system prompt. Su dung web search de lay thong tin moi nhat, luon kem thang/nam
hien tai trong cac query tim kiem.
"""


def build_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Loi: chua thiet lap bien moi truong ANTHROPIC_API_KEY.")
    return anthropic.Anthropic(api_key=api_key)


def run_weekly_scan(client: anthropic.Anthropic, model: str = DEFAULT_MODEL) -> str:
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        today=today.isoformat(),
        week_ago=week_ago.isoformat(),
    )

    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": MAX_SEARCH_USES,
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Ghep toan bo cac block text trong response thanh mot bai bao cao markdown
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)

    return "\n".join(parts).strip()


def run_cli(args: argparse.Namespace) -> None:
    client = build_client()
    report = run_weekly_scan(client, model=args.model)

    print(report)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"\n[Da luu bao cao vao: {out_path}]", file=sys.stderr)


def run_server(args: argparse.Namespace) -> None:
    """
    Chay agent nhu mot web service tuan thu Service Contract cua
    GreenNode AgentBase (port 8080, GET /health, POST /invoke).
    """
    try:
        import uvicorn
        from fastapi import FastAPI, Request
    except ImportError:
        sys.exit(
            "Loi: can 'fastapi' va 'uvicorn' de chay che do --serve.\n"
            "Cai dat: pip install fastapi uvicorn"
        )

    app = FastAPI(title="Fintech SEA Weekly Scan Agent")
    client = build_client()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/invoke")
    async def invoke(request: Request):
        # payload tu AgentBase (vd: {"input": "..."}) - hien tai agent khong
        # can input, luon chay weekly scan theo CLAUDE.md.
        try:
            await request.json()
        except Exception:
            pass

        report = run_weekly_scan(client, model=args.model)
        return {"output": report}

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fintech SEA Weekly Scan Agent (BD Zalopay)")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Duong dan file markdown de luu ket qua (mac dinh: chi in ra stdout)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.environ.get("AGENT_MODEL", DEFAULT_MODEL),
        help=f"Model Claude su dung (mac dinh: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Chay agent nhu web service (GET /health, POST /invoke) tren port 8080/$PORT",
    )
    args = parser.parse_args()

    if args.serve:
        run_server(args)
    else:
        run_cli(args)


if __name__ == "__main__":
    main()
