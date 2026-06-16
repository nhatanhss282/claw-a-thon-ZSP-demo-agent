#!/usr/bin/env python3
"""
Fintech News Weekly Scan Agent
==============================

Quet tin tuc Fintech cong khai (Dong Nam A / Viet Nam) trong 7 ngay gan nhat va
tong hop thanh ban tin theo cac truc phuc vu BD cua Zalopay:

  1. Xu huong Fintech Dong Nam A trong tuan
  2. Cap nhat san pham moi dang chu y
  3. Thi truong co chuyen dich gi (bao gom dong thai doi thu lien quan den
     segment BD dang phu trach)
  4. Chinh sach / quy dinh moi ho tro cong viec BD
  5. Goi y trao doi voi doi tac (talking points) phu hop voi segment
  6. Diem moi so voi ban tin tuan truoc (chi xuat hien neu co du lieu tuan truoc)

Khong bao gom thong tin rieng ve Zalopay.

LLM: GreenNode AI Platform MaaS (OpenAI-compatible endpoint).
Yeu cau env vars:
  - LLM_API_KEY   : API key tu GreenNode AI Platform (MaaS)
  - LLM_MODEL     : model code (vd: qwen2.5-72b-instruct) - xem trong
                     console AgentBase > Models
  - LLM_BASE_URL  : (tuy chon) mac dinh la endpoint MaaS cua GreenNode
  - TAVILY_API_KEY: API key Tavily (https://tavily.com) de thuc hien web search
  - HISTORY_DIR   : (tuy chon) thu muc luu lich su ban tin theo tuan, mac
                     dinh "/app/output/history" - dung de so sanh "diem moi
                     so voi tuan truoc"

Segment BD (tuy chon, xem SEGMENTS):
  - global_merchant     : Global merchant (Google, Apple, Grab, e-commerce
                           xuyen bien gioi...)
  - key_merchant_retail : Key merchant ban le noi dia (chuoi duoc pham,
                           sieu thi, F&B lon nhu Long Chau...)
  - soundbox_smb        : Merchant can thiet bi thanh toan (soundbox, smart POS)
  - smb                 : Merchant SMB / ho kinh doanh nho noi dia
  - general             : Tong quan, khong gioi han segment (mac dinh)

Hai che do chay:
  1. CLI (mac dinh khi co flag --output hoac --once):
       python agent.py --output report.md --segment key_merchant_retail
  2. Web service (de deploy len GreenNode AgentBase):
       python agent.py --serve
     -> lang nghe port 8080 (hoac $PORT), expose:
          GET  /health  -> {"status": "ok"}
          POST /invoke  -> body co the chua {"segment": "..."} (tuy chon),
                           chay weekly scan va tra ve {"output": "<markdown>"}
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import requests
from openai import OpenAI

DEFAULT_BASE_URL = "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"
DEFAULT_MODEL = "google/gemma-4-31b-it"
MAX_TOKENS = 4096
MAX_SEARCH_ROUNDS = 4
TAVILY_API_URL = "https://api.tavily.com/search"
DEFAULT_HISTORY_DIR = "/app/output/history"

# Cac segment BD pho bien tai Zalopay, dung de "lai" agent ve dung loai
# merchant ma BD dang phu trach (anh huong toi query tim kiem, trong tam
# truc "Thi truong chuyen dich" va "Goi y trao doi voi doi tac").
SEGMENTS = {
    "intl_digital_merchant": {
        "label": "Merchant so quoc te khong co entity VN — Canva, Meta Ads, "
                 "iQIYI, Starlink, DiDi, cac app Trung Quoc mo rong SEA...",
        "market_focus": "xu huong app Trung Quoc mo rong tai VN/SEA, "
                        "digital subscription growth tai Viet Nam, "
                        "cross-border checkout UX va acceptance rate cua "
                        "local payment method, digital content & gaming "
                        "platform them payment option noi dia, "
                        "quy dinh thue nha thau nuoc ngoai dich vu digital "
                        "(FCT/Nghi dinh 126) anh huong den merchant",
        "competitor_focus": "MoMo/VNPay da duoc accept tren platform quoc te nao; "
                             "Visa/Mastercard vs local wallet tai international "
                             "checkout; vi nao la preferred option cua cac app "
                             "Trung Quoc dang hot tai VN (Wesing, iQIYI, DiDi...); "
                             "GrabPay/ShopeePay co loi the gi voi merchant quoc te",
    },
    "key_merchant_retail": {
        "label": "Key merchant ban le noi dia (vi du: chuoi duoc pham, "
                 "sieu thi, F&B lon nhu Long Chau)",
        "market_focus": "loyalty, omnichannel, tich hop QR/POS voi he "
                        "thong ERP/CRM cua chuoi ban le, chuong trinh "
                        "khach hang than thiet, thanh toan tai cua hang",
        "competitor_focus": "dong thai cua MoMo, VNPay, ShopeePay, ngan "
                             "hang so trong hop tac voi cac chuoi ban "
                             "le/key merchant lon (loyalty, tich hop, uu dai)",
    },
    "soundbox_smb": {
        "label": "Merchant can thiet bi thanh toan (soundbox, smart POS)",
        "market_focus": "thiet bi thanh toan thong minh (soundbox, smart "
                        "POS), chi phi trien khai, trai nghiem thanh toan "
                        "tai diem ban cho ho kinh doanh nho",
        "competitor_focus": "MoMo, VNPay, ShopeePay va cac doi thu ra "
                             "mat/cap nhat thiet bi soundbox, smart POS, "
                             "chuong trinh uu dai phan cung cho ho kinh doanh",
    },
    "smb": {
        "label": "Merchant SMB / ho kinh doanh nho noi dia",
        "market_focus": "giai phap thanh toan va quan ly ban hang cho "
                        "SMB, chuong trinh ho tro/uu dai phi giao dich, "
                        "tai chinh / cho vay cho ho kinh doanh nho",
        "competitor_focus": "MoMo, VNPay, ShopeePay, cac ngan hang so voi "
                             "goi giai phap hoac uu dai danh rieng cho SMB",
    },
    "financial_institution": {
        "label": "Doi tac tai chinh — ngan hang, cong ty tai chinh, InsurTech",
        "market_focus": "open banking API, BaaS (Banking-as-a-Service), "
                        "embedded finance, BNPL funding partnership, san pham "
                        "co-branded voi ngan hang, digital lending, tich hop "
                        "InsurTech, sandbox NHNN cho hop tac fintech-bank",
        "competitor_focus": "ngan hang so VPBank Neo, MB Bank, Techcombank, "
                             "TPBank va cac vi dien tu (MoMo, VNPay) dang "
                             "trien khai BaaS hoac embedded finance; InsurTech "
                             "dang tich hop vao super-app trong khu vuc",
    },
    "telecom_utility": {
        "label": "Vien thong & Tien ich — EVN, VNPT, Viettel, nuoc, internet, bao hiem dinh ky",
        "market_focus": "so hoa hoa don dinh ky, digital billing ecosystem, "
                        "auto-debit / recurring payment, tich hop tien ich vao "
                        "super-app, thanh toan hoa don qua vi dien tu, "
                        "carrier billing",
        "competitor_focus": "MoMo, VNPay, ShopeePay tich hop EVN/VNPT/Viettel; "
                             "ngan hang so voi auto-debit hoa don; fintech nao "
                             "dang co exclusive deal voi utility provider lon",
    },
    "travel_hospitality": {
        "label": "Du lich & Lu hanh — hang khong, khach san, OTA, dat ve",
        "market_focus": "digital travel payment, checkout conversion tai OTA, "
                        "loyalty tich hop voi vi, BNPL cho travel, hang khong "
                        "noi dia thanh toan QR, cross-border travel payment, "
                        "Agoda/Booking.com/Traveloka chap nhan thanh toan noi dia",
        "competitor_focus": "MoMo/VNPay tich hop VietJet/VNA/Grab; vi nao la "
                             "preferred payment partner cua cac OTA lon; "
                             "ShopeePay/GrabPay trong he sinh thai travel SEA",
    },
    "edu_healthcare": {
        "label": "Giao duc & Y te — hoc phi, vien phi, edtech, telemedicine",
        "market_focus": "cashless hospital, thanh toan hoc phi truong dai hoc/"
                        "pho thong, edtech billing, BNPL cho y te/giao duc, "
                        "telemedicine payment, digital health wallet, "
                        "so hoa vien phi benh vien cong/tu",
        "competitor_focus": "MoMo/VNPay trong he sinh thai benh vien cong va tu; "
                             "ngan hang co deal thanh toan vien phi; fintech "
                             "dang pilot BNPL cho giao duc hoac y te tai SEA",
    },
    "gov_public": {
        "label": "Chinh phu & Dich vu cong — thue, phi hanh chinh, VNeID, De an 06",
        "market_focus": "thanh toan khong tien mat dich vu cong, tich hop "
                        "VNeID/CCCD, nop thue online, phi phat vi pham, "
                        "De an 06 cua Chinh phu, NAPAS/interbank cho dich vu "
                        "cong, quy dinh NHNN ve thanh toan hanh chinh",
        "competitor_focus": "VNPay va NAPAS la doi thu manh nhat trong thanh toan "
                             "dich vu cong; ngan hang quoc doanh (Vietcombank, "
                             "Agribank, BIDV) co loi the deal chinh phu; vi nao "
                             "dang co tich hop cong dich vu cong quoc gia",
    },
    "intl_psp": {
        "label": "Doi tac PSP quoc te — Boku, dLocal, EBANX, HitPay, Pagsmile, "
                 "DANAL, Waffo... (B2B2C: 1 PSP mang N merchant vao)",
        "market_focus": "carrier billing (Boku) va mo rong tai SEA, "
                        "emerging market PSP (dLocal, EBANX, Pagsmile) tiep can "
                        "VN/SEA, xu huong hop nhat PSP trong khu vuc, "
                        "quy dinh thanh toan xuyen bien gioi NHNN (Thong tu 39), "
                        "FX settlement & conversion, co che noi la settlement "
                        "cho PSP nuoc ngoai, chuan ky thuat API/SDK tich hop PSP",
        "competitor_focus": "VNPay/OnePay da co quan he voi PSP quoc te nao; "
                             "OnlyPay, CTIN PAY dang lam gi voi PSP quoc te; "
                             "ngan hang nao dang la settlement partner cho "
                             "dLocal/EBANX/Pagsmile tai VN; MoMo xu ly carrier "
                             "billing (App Store/Google Play) theo co che nao",
    },
    "general": {
        "label": "Tong quan (khong gioi han segment cu the)",
        "market_focus": "Fintech Dong Nam A va Viet Nam noi chung",
        "competitor_focus": "dong thai chung cua cac vi dien tu va fintech "
                             "lon trong khu vuc",
    },
}

PRODUCT_CATEGORIES = {
    "payment": {
        "label": "Thanh toan (QR / POS / Digital Wallet)",
        "focus": "trai nghiem thanh toan, QR code, contactless, NFC, checkout UX, "
                 "payment flow, super-app integration",
        "competitor_focus": "tinh nang thanh toan moi cua MoMo, VNPay, ShopeePay, "
                            "GrabPay, GoPay, TrueMoney, PromptPay",
    },
    "lending": {
        "label": "Tin dung & BNPL",
        "focus": "BNPL, tin dung vi mo, credit scoring, loan origination UX, "
                 "embedded lending, buy-now-pay-later",
        "competitor_focus": "san pham cho vay/BNPL cua Kredivo, Akulaku, Home Credit, "
                            "MoMo PayLater, SPayLater, GrabPayLater",
    },
    "loyalty": {
        "label": "Loyalty & Rewards",
        "focus": "chuong trinh tich diem, cashback, gamification, loyalty platform, "
                 "personalization, engagement mechanic",
        "competitor_focus": "chuong trinh loyalty cua cac vi dien tu, ngan hang so, "
                            "VNLIFE/VNPAY, Be Group, Grab Rewards",
    },
    "cross_border": {
        "label": "Thanh toan xuyen bien gioi",
        "focus": "cross-border payment, multi-currency wallet, remittance UX, "
                 "FX rate transparency, international checkout",
        "competitor_focus": "tinh nang thanh toan quoc te cua Wise, GrabPay, "
                            "Ant Group/Alipay+, PayMongo, Razorpay",
    },
    "general": {
        "label": "Tong quan san pham Fintech",
        "focus": "product innovation, UX/UI trends, super-app, embedded finance, "
                 "AI trong fintech product",
        "competitor_focus": "product updates tong quat cua cac fintech lon trong khu vuc",
    },
}

SYSTEM_PROMPT = """\
Ban la mot research analyst ho tro Business Development (BD) cua Zalopay.

Nhiem vu: quet tin tuc Fintech cong khai tren internet trong 7 ngay gan nhat
va tong hop thanh mot ban tin ngan, actionable, theo dung cac truc duoc neu
trong yeu cau cua user (KHONG bao gom thong tin rieng ve Zalopay).

Cac truc co the gom:
1. Xu huong Fintech Dong Nam A trong tuan (AI, embedded finance, blockchain,
   ngan hang so, financial inclusion, thanh toan...)
2. Cap nhat san pham moi dang chu y (vi dien tu, QR, ngan hang so, BNPL,
   thanh toan xuyen bien gioi...) o Viet Nam va Dong Nam A
3. Thi truong co chuyen dich gi (tang truong, M&A, hop tac ngan hang -
   fintech, thay doi canh tranh). Trong truc nay, luon co mot phan rieng
   "Dong thai doi thu" tap trung vao segment BD duoc neu trong yeu cau.
4. Chinh sach / quy dinh moi ban hanh ho tro cong viec BD (sandbox, luat
   bao ve du lieu, quy dinh NHNN, giay phep trung gian thanh toan,
   stablecoin/crypto...)
5. Goi y trao doi voi doi tac (talking points): dua tren tin tuc da tim
   duoc va segment BD dang phu trach, de xuat 2-3 "conversation starter"
   hoac "value proposition angle" cu the, co the dung ngay khi gap partner.
6. Diem moi so voi ban tin tuan truoc: CHI viet truc nay neu yeu cau co
   cung cap noi dung ban tin tuan truoc. Chi ra nhung thong tin moi / thay
   doi so voi ban tin do, khong copy lai noi dung cu.

Quy tac:
- Su dung tool "web_search" de tim tin tuc moi nhat. Luon dung tu khoa kem
  thang/nam hien tai de tranh ket qua loi thoi. Goi tool nhieu lan voi cac
  truy van khac nhau cho tung truc, uu tien tin lien quan den segment BD
  duoc neu trong yeu cau (neu co).
- Moi truc: 3-5 bullet, suc tich, di thang vao thong tin.
- Moi bullet kem nguon (link) ro rang.
- Sau moi truc (tru truc 5 va 6), neu phu hop, them mot dong "Goi y cho BD:"
  - goc ap dung thuc te.
- Khong lap lai thong tin giua cac truc.
- KHONG dua thong tin ve Zalopay (san pham, doi tac, tin tuc rieng cua
  Zalopay).
- Cuoi ban tin: ghi ro ngay tong hop, pham vi thoi gian (7 ngay gan nhat) va
  segment BD (neu co).
- Van phong: tieng Viet, ngan gon, chuyen nghiep.
- Output dang Markdown, voi heading ro rang cho moi truc duoc yeu cau.
"""

PRODUCT_SYSTEM_PROMPT = """\
Ban la mot research analyst ho tro team Product cua Zalopay.

Nhiem vu: quet tin tuc Fintech cong khai tren internet trong 7 ngay gan nhat
va tong hop thanh mot ban tin ngan, actionable, giup Product team nam duoc xu
huong, dong thai doi thu va co hoi san pham (KHONG bao gom thong tin rieng ve
Zalopay).

Cac truc co the gom:
1. Xu huong san pham & UX Fintech SEA: AI trong product, embedded finance,
   super-app, payment UX innovations, gamification, personalization...
2. Tinh nang / san pham moi cua doi thu: mo ta chi tiet tinh nang, flow nguoi
   dung, gia tri mang lai. Tap trung vao category san pham duoc neu trong yeu cau.
3. Benchmark & so sanh tinh nang: danh gia kha nang tinh nang tuong tu giua
   cac player de Product co buc tranh canh tranh ro rang.
4. Insight hanh vi nguoi dung & adoption: data/bao cao ve cach nguoi dung SEA
   dang su dung fintech, friction points, pain points, adoption rate.
5. Co hoi san pham (Product Opportunities): tu tin tuc da tim duoc va category
   dang phu trach, de xuat 2-3 huong phat trien tinh nang hoac cai tien UX cu
   the ma Product co the tham khao.
6. Diem moi so voi ban tin tuan truoc: CHI viet truc nay neu yeu cau co cung cap
   noi dung ban tin tuan truoc. Chi ra tinh nang/xu huong moi, khong copy lai cu.

Quy tac:
- Su dung tool "web_search" de tim tin tuc moi nhat. Luon kem thang/nam hien tai.
  Goi tool nhieu lan voi cac truy van khac nhau, uu tien tim theo category san pham.
- Moi truc: 3-5 bullet, suc tich, tap trung vao chi tiet san pham cu the.
- Moi bullet kem nguon (link) ro rang.
- Sau moi truc (tru truc 5 va 6), them mot dong "Goi y cho Product:" - goc ap dung.
- KHONG dua thong tin ve Zalopay (san pham, doi tac, tin tuc rieng).
- Cuoi ban tin: ghi ro ngay tong hop, pham vi thoi gian va category san pham.
- Van phong: tieng Viet, ngan gon, chuyen nghiep, focus vao chi tiet san pham.
- Output dang Markdown, voi heading ro rang cho moi truc duoc yeu cau.
"""

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Tim kiem thong tin moi nhat tren internet. Tra ve danh sach ket qua gom title, url, va noi dung tom tat.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Truy van tim kiem, nen kem thang/nam de co ket qua moi nhat",
                }
            },
            "required": ["query"],
        },
    },
}


def get_segment(segment_key: str) -> dict:
    return SEGMENTS.get(segment_key, SEGMENTS["general"])


def get_product_category(category_key: str) -> dict:
    return PRODUCT_CATEGORIES.get(category_key, PRODUCT_CATEGORIES["general"])


def get_system_prompt(team: str) -> str:
    return PRODUCT_SYSTEM_PROMPT if team == "product" else SYSTEM_PROMPT


def _market_line(market: str) -> str:
    if market == "vn":
        return "Pham vi dia ly: chi tap trung vao Viet Nam."
    if market == "sea_ex_vn":
        return ("Pham vi dia ly: Dong Nam A ngoai Viet Nam "
                "(Singapore, Indonesia, Thailand, Malaysia, Philippines...).")
    return "Pham vi dia ly: Dong Nam A (SEA) bao gom Viet Nam."


def _build_bd_prompt(
    today: datetime.date,
    week_ago: datetime.date,
    segment_key: str,
    previous_report: str | None = None,
    market: str = "sea",
    extra_keywords: str = "",
) -> str:
    seg = get_segment(segment_key)
    lines = [
        f"Hom nay la {today.isoformat()}. Hay quet tin tuc Fintech "
        f"trong 7 ngay gan nhat (tu {week_ago.isoformat()} den {today.isoformat()}).",
        "",
        f"Segment BD dang phu trach: {seg['label']}.",
        f"- Khi viet truc 1 va truc 3, uu tien: {seg['market_focus']}.",
        f"- Trong truc 3, them phan 'Dong thai doi thu' tap trung vao: {seg['competitor_focus']}.",
        "", _market_line(market),
    ]
    if extra_keywords.strip():
        lines.append(f"Tu khoa bo sung: {extra_keywords.strip()}.")
    lines += [
        "",
        "Tong hop ban tin gom 5 truc chinh: (1) Xu huong Fintech SEA, "
        "(2) San pham moi, (3) Thi truong chuyen dich (gom dong thai doi thu), "
        "(4) Chinh sach/quy dinh, (5) Goi y trao doi voi doi tac (talking points).",
    ]
    if previous_report:
        lines += [
            "",
            "Duoi day la ban tin tuan truoc. Hay them truc 6 'Diem moi so voi "
            "tuan truoc', chi ra thong tin moi/thay doi (khong copy lai noi dung cu):",
            "--- BAN TIN TUAN TRUOC ---", previous_report, "--- HET ---",
        ]
    lines += ["", "Su dung web_search, luon kem thang/nam hien tai trong query."]
    return "\n".join(lines)


def _build_product_prompt(
    today: datetime.date,
    week_ago: datetime.date,
    category_key: str,
    previous_report: str | None = None,
    market: str = "sea",
    extra_keywords: str = "",
) -> str:
    cat = get_product_category(category_key)
    lines = [
        f"Hom nay la {today.isoformat()}. Hay quet tin tuc Fintech "
        f"trong 7 ngay gan nhat (tu {week_ago.isoformat()} den {today.isoformat()}).",
        "",
        f"Category san pham dang phu trach: {cat['label']}.",
        f"- Uu tien tim kiem va phan tich: {cat['focus']}.",
        f"- Theo doi doi thu trong category nay: {cat['competitor_focus']}.",
        "", _market_line(market),
    ]
    if extra_keywords.strip():
        lines.append(f"Tu khoa bo sung: {extra_keywords.strip()}.")
    lines += [
        "",
        "Tong hop ban tin gom 5 truc chinh: (1) Xu huong san pham & UX Fintech SEA, "
        "(2) Tinh nang/san pham moi cua doi thu, (3) Benchmark & so sanh tinh nang, "
        "(4) Insight hanh vi nguoi dung & adoption, "
        "(5) Co hoi san pham (Product Opportunities) phu hop voi category tren.",
    ]
    if previous_report:
        lines += [
            "",
            "Duoi day la ban tin tuan truoc (cung category). Hay them truc 6 "
            "'Diem moi so voi tuan truoc', chi ra tinh nang/xu huong moi xuat hien:",
            "--- BAN TIN TUAN TRUOC ---", previous_report, "--- HET ---",
        ]
    lines += ["", "Su dung web_search, luon kem thang/nam hien tai trong query."]
    return "\n".join(lines)


def build_user_prompt(
    today: datetime.date,
    week_ago: datetime.date,
    team: str = "bd",
    segment_key: str = "general",
    product_category: str = "general",
    previous_report: str | None = None,
    market: str = "sea",
    extra_keywords: str = "",
) -> str:
    if team == "product":
        return _build_product_prompt(
            today, week_ago, product_category, previous_report, market, extra_keywords
        )
    return _build_bd_prompt(
        today, week_ago, segment_key, previous_report, market, extra_keywords
    )


def build_client() -> OpenAI:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        sys.exit("Loi: chua thiet lap bien moi truong LLM_API_KEY.")
    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url)


def web_search(query: str, max_results: int = 5) -> str:
    """Tim kiem web bang Tavily Search API."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "Loi: chua thiet lap bien moi truong TAVILY_API_KEY."
    try:
        resp = requests.post(
            TAVILY_API_URL,
            json={"api_key": api_key, "query": query, "max_results": max_results},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return "Khong tim thay ket qua nao."
        lines = []
        for r in results:
            title = r.get("title", "")
            url = r.get("url", "")
            content = r.get("content", "")
            lines.append(f"- {title} ({url})\n  {content}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Loi khi goi Tavily Search: {exc}"


def _history_dir() -> Path:
    return Path(os.environ.get("HISTORY_DIR", DEFAULT_HISTORY_DIR))


def load_previous_report(segment_key: str, today: datetime.date) -> str | None:
    """Tim ban tin gan nhat (truoc ngay hom nay) cua cung segment."""
    hist_dir = _history_dir()
    if not hist_dir.exists():
        return None

    candidates = sorted(hist_dir.glob(f"{segment_key}_*.md"), reverse=True)
    today_suffix = f"{segment_key}_{today.isoformat()}.md"

    for path in candidates:
        if path.name == today_suffix:
            continue
        try:
            content = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if content:
            return content

    return None


def save_report(segment_key: str, today: datetime.date, report: str) -> None:
    hist_dir = _history_dir()
    try:
        hist_dir.mkdir(parents=True, exist_ok=True)
        path = hist_dir / f"{segment_key}_{today.isoformat()}.md"
        path.write_text(report, encoding="utf-8")
    except Exception as exc:
        # Khong de loi luu lich su lam fail ca request
        print(f"[warn] Khong the luu lich su ban tin: {exc}", file=sys.stderr)


def run_weekly_scan(
    client: OpenAI,
    model: str,
    segment: str = "general",
    market: str = "sea",
    extra_keywords: str = "",
    team: str = "bd",
    product_category: str = "general",
) -> str:
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)

    history_key = f"product_{product_category}" if team == "product" else segment
    previous_report = load_previous_report(history_key, today)
    user_prompt = build_user_prompt(
        today, week_ago,
        team=team, segment_key=segment, product_category=product_category,
        previous_report=previous_report, market=market, extra_keywords=extra_keywords,
    )
    system_prompt = get_system_prompt(team)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for _ in range(MAX_SEARCH_ROUNDS):
        response = client.chat.completions.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=messages,
            tools=[WEB_SEARCH_TOOL],
            tool_choice="auto",
        )

        choice = response.choices[0]
        message = choice.message
        messages.append(message.model_dump(exclude_none=True))

        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            report = (message.content or "").strip()
            save_report(history_key, today, report)
            return report

        for tool_call in tool_calls:
            args = {}
            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                pass

            query = args.get("query", "")
            result = web_search(query)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    # Het so luot search cho phep - yeu cau model tong hop voi thong tin da co
    messages.append(
        {
            "role": "user",
            "content": "Hay tong hop ban tin Markdown ngay bay gio dua tren thong tin da tim duoc.",
        }
    )
    final = client.chat.completions.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=messages,
    )
    report = (final.choices[0].message.content or "").strip()
    save_report(history_key, today, report)
    return report


def run_cli(args: argparse.Namespace) -> None:
    client = build_client()
    report = run_weekly_scan(
        client,
        model=args.model,
        segment=args.segment,
        market=args.market,
        extra_keywords=args.extra_keywords,
        team=args.team,
        product_category=args.product_category,
    )

    print(report)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"\n[Da luu bao cao vao: {out_path}]", file=sys.stderr)


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fintech News Weekly Scan | Zalopay</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;background:#F5F7FF;color:#111827;min-height:100vh;line-height:1.5}
.topnav{background:#fff;border-bottom:1.5px solid #E5E7EB;padding:0 32px;height:56px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100}
.nav-logo{display:flex;align-items:center;text-decoration:none;font-size:21px;font-weight:800;letter-spacing:-.5px}
.logo-z{color:#003FD4}.logo-p{color:#09B24E}
.nav-div{width:1px;height:22px;background:#E5E7EB}
.nav-prod{font-size:13px;font-weight:500;color:#6B7280}
.hero{background:linear-gradient(145deg,#003FD4 0%,#00218F 100%);color:#fff;padding:44px 24px 50px;text-align:center}
.hero-tag{display:inline-block;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.25);border-radius:99px;font-size:11px;font-weight:600;letter-spacing:1.1px;text-transform:uppercase;padding:4px 14px;margin-bottom:16px}
.hero h1{font-size:28px;font-weight:800;margin-bottom:12px;letter-spacing:-.5px}
.hero-sub{font-size:14px;opacity:.85;max-width:560px;margin:0 auto 24px;line-height:1.7}
.team-tabs{display:flex;gap:8px;justify-content:center;margin-bottom:16px}
.team-tab{background:rgba(255,255,255,.12);border:1.5px solid rgba(255,255,255,.2);border-radius:99px;padding:6px 18px;font-size:13px;font-weight:600;cursor:pointer;color:#fff;transition:all .15s}
.team-tab.active{background:#fff;color:#003FD4;border-color:#fff}
.chips{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:700px;margin:0 auto}
.chip{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);border-radius:8px;padding:6px 12px;font-size:12px;font-weight:500}
.bd-chips,.product-chips{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:700px;margin:0 auto}
.product-chips{display:none}
.container{max-width:820px;margin:0 auto;padding:28px 16px 60px}
.card{background:#fff;border-radius:12px;padding:24px;border:1px solid #E5E7EB;margin-bottom:16px}
.sec-label{font-size:11px;font-weight:700;color:#003FD4;text-transform:uppercase;letter-spacing:.8px;margin-bottom:18px;display:flex;align-items:center;gap:8px}
.sec-label::before{content:'';display:block;width:3px;height:13px;background:#003FD4;border-radius:2px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
@media(max-width:600px){.form-grid{grid-template-columns:1fr}}
.field label{display:block;font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px}
.field-note{font-size:11px;color:#9CA3AF;margin-top:5px}
select,input[type=text]{width:100%;padding:10px 12px;border:1.5px solid #E5E7EB;border-radius:8px;font-size:14px;color:#111827;background:#fff;transition:border-color .15s,box-shadow .15s}
select{appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%236B7280' d='M6 8L0 0h12z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center;cursor:pointer}
select:focus,input[type=text]:focus{outline:none;border-color:#003FD4;box-shadow:0 0 0 3px rgba(0,63,212,.1)}
.field-full{margin-bottom:18px}
.team-field{display:block}
.product-field{display:none}
.run-btn{display:block;width:100%;background:#003FD4;color:#fff;border:none;padding:13px;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;transition:background .15s,transform .1s}
.run-btn:hover:not(:disabled){background:#002BAD;transform:translateY(-1px)}
.run-btn:active:not(:disabled){transform:translateY(0)}
.run-btn:disabled{opacity:.55;cursor:not-allowed;transform:none}
.progress{display:none;margin-top:18px}
.pbar-track{height:3px;background:#E5EDFF;border-radius:2px;overflow:hidden}
.pbar-fill{height:100%;width:40%;background:linear-gradient(90deg,#003FD4,#09B24E);border-radius:2px;animation:bar 1.6s ease-in-out infinite}
@keyframes bar{0%{transform:translateX(-150%)}100%{transform:translateX(350%)}}
.pstatus{font-size:13px;color:#6B7280;margin-top:10px;display:flex;align-items:center;gap:8px}
.pdot{width:6px;height:6px;border-radius:50%;background:#003FD4;animation:dot 1.4s ease-in-out infinite}
@keyframes dot{0%,100%{opacity:1}50%{opacity:.25}}
.err{display:none;margin-top:14px;background:#FEF2F2;border:1px solid #FECACA;border-radius:8px;padding:12px 16px;color:#B91C1C;font-size:13px}
.result-card{display:none}
.result-top{display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:14px;border-bottom:1px solid #F3F4F6;margin-bottom:20px}
.result-top h2{font-size:16px;font-weight:700;color:#111827}
.result-meta{font-size:12px;color:#9CA3AF;margin-top:4px}
.dl-btn{flex-shrink:0;background:#F3F4F6;color:#374151;border:1.5px solid #E5E7EB;padding:7px 16px;border-radius:7px;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s;margin-left:12px}
.dl-btn:hover{background:#E5EDFF;border-color:#003FD4;color:#003FD4}
#report{font-size:14px;line-height:1.8;color:#1F2937}
#report h1{font-size:20px;font-weight:800;margin:0 0 16px;color:#111827}
#report h2{font-size:16px;font-weight:700;margin:26px 0 10px;color:#003FD4;border-bottom:1px solid #EEF4FF;padding-bottom:7px}
#report h3{font-size:14px;font-weight:700;margin:18px 0 8px;color:#374151}
#report ul{padding-left:20px}
#report li{margin-bottom:10px}
#report p{margin-bottom:10px}
#report a{color:#0052E3;text-decoration:none;border-bottom:1px solid transparent;transition:border-color .1s}
#report a:hover{border-bottom-color:#0052E3}
#report strong{font-weight:700;color:#111827}
#report em{font-style:italic;color:#6B7280}
#report hr{border:none;border-top:1px solid #F3F4F6;margin:22px 0}
#report blockquote{border-left:3px solid #003FD4;margin:14px 0;padding:10px 16px;background:#F5F7FF;border-radius:0 8px 8px 0;color:#4B5563;font-style:italic}
#report code{background:#F3F4F6;padding:2px 6px;border-radius:4px;font-size:13px;font-family:monospace}
</style>
</head>
<body>
<nav class="topnav">
  <a href="/" class="nav-logo"><span class="logo-z">Zalo</span><span class="logo-p">pay</span></a>
  <div class="nav-div"></div>
  <span class="nav-prod">Fintech News Weekly Scan</span>
</nav>
<div class="hero">
  <div class="hero-tag">AI Research Agent</div>
  <h1>Fintech News Weekly Scan</h1>
  <p class="hero-sub">Agent tự động quét tin tức Fintech công khai mỗi tuần, tổng hợp bản tin actionable theo đúng team và mục đích sử dụng.</p>
  <div class="team-tabs">
    <button class="team-tab active" onclick="switchTeam('bd',this)">📊 BD Team</button>
    <button class="team-tab" onclick="switchTeam('product',this)">🚀 Product Team</button>
  </div>
  <div class="bd-chips">
    <div class="chip">📡 Xu hướng Fintech SEA</div>
    <div class="chip">🚀 Sản phẩm mới đáng chú ý</div>
    <div class="chip">📊 Chuyển dịch thị trường &amp; đối thủ</div>
    <div class="chip">📋 Chính sách &amp; quy định mới</div>
    <div class="chip">💡 Gợi ý trao đổi với đối tác</div>
    <div class="chip">🆕 Điểm mới vs tuần trước</div>
  </div>
  <div class="product-chips">
    <div class="chip">🎨 Xu hướng UX &amp; Product</div>
    <div class="chip">🔍 Tính năng mới của đối thủ</div>
    <div class="chip">⚖️ Benchmark &amp; so sánh tính năng</div>
    <div class="chip">👥 Insight hành vi người dùng</div>
    <div class="chip">💡 Cơ hội sản phẩm (Product Ops)</div>
    <div class="chip">🆕 Điểm mới vs tuần trước</div>
  </div>
</div>
<div class="container">
  <div class="card">
    <div class="sec-label">Tùy chỉnh báo cáo</div>
    <div class="form-grid">
      <div class="field team-field" id="segmentField">
        <label for="segment">Segment BD</label>
        <select id="segment">
          <option value="general">Tổng quan (General)</option>
          <optgroup label="── Merchant nội địa ──">
            <option value="key_merchant_retail">Key Merchant Bán lẻ — Long Châu, siêu thị, F&amp;B lớn</option>
            <option value="soundbox_smb">Soundbox / Smart POS</option>
            <option value="smb">SMB / Hộ kinh doanh nhỏ nội địa</option>
          </optgroup>
          <optgroup label="── Quốc tế ──">
            <option value="intl_digital_merchant">Merchant số quốc tế — Canva, Meta Ads, iQIYI, DiDi, app Trung Quốc mở rộng SEA...</option>
            <option value="intl_psp">Đối tác PSP quốc tế — Boku, dLocal, EBANX, HitPay, Pagsmile, DANAL...</option>
          </optgroup>
          <optgroup label="── Đối tác chiến lược ──">
            <option value="financial_institution">Đối tác Tài chính — Ngân hàng, FinTech lending, InsurTech</option>
            <option value="telecom_utility">Viễn thông &amp; Tiện ích — EVN, VNPT, Viettel, hoá đơn định kỳ</option>
            <option value="travel_hospitality">Du lịch &amp; Lữ hành — Hàng không, OTA, khách sạn</option>
            <option value="edu_healthcare">Giáo dục &amp; Y tế — Học phí, viện phí, edtech, telemedicine</option>
            <option value="gov_public">Chính phủ &amp; Dịch vụ công — Thuế, VNeID, Đề án 06</option>
          </optgroup>
        </select>
        <div class="field-note">Ảnh hưởng đến tiêu điểm thị trường &amp; talking point</div>
      </div>
      <div class="field product-field" id="categoryField">
        <label for="category">Category sản phẩm</label>
        <select id="category">
          <option value="general">Tổng quan Fintech</option>
          <option value="payment">Thanh toán (QR / POS / Digital Wallet)</option>
          <option value="lending">Tín dụng &amp; BNPL</option>
          <option value="loyalty">Loyalty &amp; Rewards</option>
          <option value="cross_border">Thanh toán xuyên biên giới</option>
        </select>
        <div class="field-note">Ảnh hưởng đến tiêu điểm sản phẩm &amp; benchmark đối thủ</div>
      </div>
      <div class="field">
        <label for="market">Phạm vi địa lý</label>
        <select id="market">
          <option value="sea">Việt Nam + Đông Nam Á (SEA)</option>
          <option value="vn">Chỉ Việt Nam</option>
          <option value="sea_ex_vn">SEA (không tính Việt Nam)</option>
        </select>
        <div class="field-note">Giới hạn nguồn tin theo thị trường</div>
      </div>
    </div>
    <div class="field-full field">
      <label for="keywords">Từ khóa bổ sung (tùy chọn)</label>
      <input type="text" id="keywords" placeholder="VD: BNPL, cross-border, Open Banking, stablecoin...">
      <div class="field-note">Agent sẽ ưu tiên tìm thêm các chủ đề bạn quan tâm trong tuần này</div>
    </div>
    <button class="run-btn" id="runBtn" onclick="runScan()">Chạy báo cáo</button>
    <div class="progress" id="progress">
      <div class="pbar-track"><div class="pbar-fill"></div></div>
      <div class="pstatus"><div class="pdot"></div><span id="pmsg">Đang khởi tạo...</span></div>
    </div>
    <div class="err" id="errBox"></div>
  </div>
  <div class="card result-card" id="resultCard">
    <div class="result-top">
      <div>
        <h2 id="rTitle">Bản tin tuần</h2>
        <div class="result-meta" id="rMeta"></div>
      </div>
      <button class="dl-btn" onclick="dlReport()">&#8595; Tải .md</button>
    </div>
    <div id="report"></div>
  </div>
</div>
<script>
const BD_MSGS=['Đang tìm kiếm tin tức Fintech SEA...','Đang phân tích xu hướng thị trường...','Đang tổng hợp sản phẩm & tính năng mới...','Đang rà soát chính sách & quy định...','Đang theo dõi động thái đối thủ...','Đang soạn gợi ý trao đổi đối tác...','Hoàn thiện bản tin, sắp xong...'];
const PROD_MSGS=['Đang tìm kiếm tính năng mới của đối thủ...','Đang phân tích xu hướng UX / Product...','Đang benchmark so sánh tính năng...','Đang tổng hợp insight hành vi người dùng...','Đang soạn cơ hội sản phẩm...','Hoàn thiện bản tin Product, sắp xong...'];
const SEG={'general':'Tổng quan','intl_digital_merchant':'Merchant số quốc tế','intl_psp':'Đối tác PSP quốc tế','key_merchant_retail':'Key Merchant Bán lẻ','soundbox_smb':'Soundbox / Smart POS','smb':'SMB / Hộ KD nhỏ','financial_institution':'Đối tác Tài chính','telecom_utility':'Viễn thông & Tiện ích','travel_hospitality':'Du lịch & Lữ hành','edu_healthcare':'Giáo dục & Y tế','gov_public':'Dịch vụ công'};
const CAT={'general':'Tổng quan Fintech','payment':'Thanh toán','lending':'Tín dụng & BNPL','loyalty':'Loyalty & Rewards','cross_border':'Thanh toán xuyên biên giới'};
const MKT={'sea':'VN + SEA','vn':'Việt Nam','sea_ex_vn':'SEA (ngoài VN)'};
let md='',curTeam='bd';
const sl=ms=>new Promise(r=>setTimeout(r,ms));
function setMsg(i){const msgs=curTeam==='product'?PROD_MSGS:BD_MSGS;document.getElementById('pmsg').textContent=msgs[i%msgs.length]}
function showErr(m){const b=document.getElementById('errBox');b.textContent='⚠ '+m;b.style.display='block'}
function switchTeam(t,btn){
  curTeam=t;
  document.querySelectorAll('.team-tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelector('.bd-chips').style.display=t==='bd'?'flex':'none';
  document.querySelector('.product-chips').style.display=t==='product'?'flex':'none';
  document.getElementById('segmentField').style.display=t==='bd'?'block':'none';
  document.getElementById('categoryField').style.display=t==='product'?'block':'none';
}
async function runScan(){
  const team=curTeam;
  const seg=document.getElementById('segment').value;
  const cat=document.getElementById('category').value;
  const mkt=document.getElementById('market').value;
  const kw=document.getElementById('keywords').value.trim();
  const btn=document.getElementById('runBtn');
  const prog=document.getElementById('progress');
  const err=document.getElementById('errBox');
  const rc=document.getElementById('resultCard');
  btn.disabled=true;rc.style.display='none';err.style.display='none';prog.style.display='block';setMsg(0);
  try{
    const payload={team,market:mkt};
    if(team==='bd') payload.segment=seg; else payload.product_category=cat;
    if(kw) payload.extra_keywords=kw;
    const r=await fetch('/invoke',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const d=await r.json();
    if(!d.job_id)throw new Error(d.error||'Không nhận được job_id');
    await poll(d.job_id,team,seg,cat,mkt,kw);
  }catch(e){showErr(e.message);prog.style.display='none';btn.disabled=false}
}
async function poll(id,team,seg,cat,mkt,kw){
  const btn=document.getElementById('runBtn');const prog=document.getElementById('progress');
  let t=0;
  while(true){
    setMsg(t++);await sl(4000);
    const r=await fetch('/result/'+id);const d=await r.json();
    if(d.status==='done'){prog.style.display='none';btn.disabled=false;showRpt(d.output,team,seg,cat,mkt,kw);return}
    if(d.status==='error'){prog.style.display='none';showErr(d.output);btn.disabled=false;return}
  }
}
function showRpt(content,team,seg,cat,mkt,kw){
  md=content;
  const label=team==='product'?(CAT[cat]||cat):(SEG[seg]||seg);
  const teamLabel=team==='product'?'Product':'BD';
  document.getElementById('rTitle').textContent=`Bản tin tuần — ${teamLabel} · ${label}`;
  const meta=[MKT[mkt]||mkt];if(kw)meta.push('Keywords: '+kw);
  document.getElementById('rMeta').textContent=meta.join(' · ');
  document.getElementById('report').innerHTML=marked.parse(content);
  const c=document.getElementById('resultCard');c.style.display='block';
  c.scrollIntoView({behavior:'smooth',block:'start'});
}
function dlReport(){
  const b=new Blob([md],{type:'text/markdown;charset=utf-8'});
  const a=document.createElement('a');a.href=URL.createObjectURL(b);
  a.download='fintech_sea_'+new Date().toISOString().slice(0,10)+'.md';a.click();
}
</script>
</body>
</html>"""


def run_server(args: argparse.Namespace) -> None:
    """
    Chay agent nhu mot web service tuan thu Service Contract cua
    GreenNode AgentBase (port 8080, GET /health, POST /invoke).
    """
    try:
        import uvicorn
        from fastapi import FastAPI, Request
        from fastapi.responses import HTMLResponse
    except ImportError:
        sys.exit(
            "Loi: can 'fastapi' va 'uvicorn' de chay che do --serve.\n"
            "Cai dat: pip install fastapi uvicorn"
        )

    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    app = FastAPI(title="Fintech News Weekly Scan Agent")
    client = build_client()
    default_model = args.model
    executor = ThreadPoolExecutor(max_workers=4)

    # job store: job_id -> {"status": "running"|"done"|"error", "result": ..., "segment": ...}
    jobs: dict = {}

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTML_PAGE

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/invoke")
    async def invoke(request: Request):
        # payload tu AgentBase, vi du:
        #   {"segment": "key_merchant_retail"}
        #   {"segment": "soundbox_smb", "model": "qwen2.5-72b-instruct"}
        payload = {}
        try:
            payload = await request.json()
        except Exception:
            pass

        p = payload if isinstance(payload, dict) else {}
        team = p.get("team", "bd")
        if team not in ("bd", "product"):
            team = "bd"
        segment = p.get("segment", "general")
        if segment not in SEGMENTS:
            segment = "general"
        product_category = p.get("product_category", "general")
        if product_category not in PRODUCT_CATEGORIES:
            product_category = "general"
        market = p.get("market", "sea")
        if market not in ("sea", "vn", "sea_ex_vn"):
            market = "sea"
        extra_keywords = str(p.get("extra_keywords", ""))
        model = p.get("model") or default_model

        # Sinh job_id va chay background de tranh gateway timeout
        import uuid
        job_id = str(uuid.uuid4())
        jobs[job_id] = {
            "status": "running", "team": team, "segment": segment,
            "product_category": product_category, "market": market, "result": None,
        }

        loop = asyncio.get_event_loop()

        def _run():
            try:
                report = run_weekly_scan(
                    client, model=model, segment=segment,
                    market=market, extra_keywords=extra_keywords,
                    team=team, product_category=product_category,
                )
                jobs[job_id]["result"] = report
                jobs[job_id]["status"] = "done"
            except Exception as e:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["result"] = str(e)

        loop.run_in_executor(executor, _run)

        return {"job_id": job_id, "status": "running", "team": team, "segment": segment,
                "market": market, "message": "Agent dang xu ly. Goi GET /result/{job_id} de lay ket qua."}

    @app.get("/result/{job_id}")
    async def get_result(job_id: str):
        if job_id not in jobs:
            return {"error": "job_id khong ton tai"}, 404
        job = jobs[job_id]
        if job["status"] == "running":
            return {"job_id": job_id, "status": "running", "message": "Dang xu ly, thu lai sau 30 giay..."}
        return {
            "job_id": job_id, "status": job["status"],
            "team": job.get("team", "bd"), "segment": job["segment"],
            "product_category": job.get("product_category", "general"),
            "market": job.get("market", "sea"), "output": job["result"],
        }

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fintech News Weekly Scan Agent (Zalopay)")
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
        default=os.environ.get("LLM_MODEL", DEFAULT_MODEL),
        help=f"Model code tren GreenNode MaaS (mac dinh: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--segment",
        type=str,
        default=os.environ.get("BD_SEGMENT", "general"),
        choices=sorted(SEGMENTS.keys()),
        help="Segment BD dang phu trach, dung de uu tien tin tuc va goi y talking point (mac dinh: general)",
    )
    parser.add_argument(
        "--market",
        type=str,
        default=os.environ.get("BD_MARKET", "sea"),
        choices=["sea", "vn", "sea_ex_vn"],
        help="Pham vi dia ly: sea (VN+SEA, mac dinh), vn (chi VN), sea_ex_vn (SEA khong tinh VN)",
    )
    parser.add_argument(
        "--extra-keywords",
        dest="extra_keywords",
        type=str,
        default=os.environ.get("BD_EXTRA_KEYWORDS", ""),
        help="Tu khoa bo sung de agent uu tien tim kiem (vi du: 'BNPL, Open Banking')",
    )
    parser.add_argument(
        "--team",
        type=str,
        default=os.environ.get("AGENT_TEAM", "bd"),
        choices=["bd", "product"],
        help="Team su dung agent: bd (mac dinh) hoac product",
    )
    parser.add_argument(
        "--product-category",
        dest="product_category",
        type=str,
        default=os.environ.get("PRODUCT_CATEGORY", "general"),
        choices=sorted(PRODUCT_CATEGORIES.keys()),
        help="Category san pham khi chay voi --team product (mac dinh: general)",
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
