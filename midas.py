import os
import ssl
import html
import statistics
from datetime import datetime, timedelta

from pytefas import Crawler, TefasAPIError, TefasRateLimitError

try:
    import yfinance as yf
    YFINANCE_VAR = True
except ImportError:
    YFINANCE_VAR = False

# ==============================================================================
# BU SCRIPT main.py / BES SİSTEMİNDEN TAMAMEN BAĞIMSIZDIR.
# Ayrı veri, ayrı çıktı dosyası (public/midas.html), ayrı geçmiş kaydı.
# ==============================================================================
bugun = datetime.now()
tarih_str = bugun.strftime('%d-%m-%Y')
REQUEST_TIMEOUT = 5
MAX_RESPONSE_BYTES = 200_000

# ------------------------------------------------------------------------------
# ALIM VERİLERİ — Midas ekran görüntüsünden alınmıştır. Yeni alım yaptıkça
# ilgili listeye yeni bir satır eklemen yeterli, geri kalan hesap otomatik.
# Format: (kod, ad, tarih, fiyat, lot, tutar)
# ------------------------------------------------------------------------------
FON_ALIMLARI = [
    ("TTE", "Bist Teknoloji Ağırlık Sınırlamalı Endeksi Hisse Senedi (TL) Fonu", "2025-12-29", 0.995457, 1506, 1500.00),
    ("ICZ", "Ak Portföy Teknoloji Şirketleri Hisse Senedi Fonu", "2025-12-29", 5.906404, 253, 1500.00),
    ("DTZ", "Ak Portföy Robotik Teknolojiler Değişken Fon", "2025-12-29", 4.027914, 248, 1000.00),
    ("MTV", "Ak Portföy Metaverse ve Dijital Yaşam Teknolojileri Fon", "2025-12-29", 4.345247, 230, 1000.00),
    ("AOY", "Ak Portföy Alternatif Enerji Yabancı Hisse Senedi Fonu", "2025-12-29", 0.308633, 6480, 2000.00),
    ("AFS", "Ak Portföy Sağlık Sektörü Yabancı Hisse Senedi Fonu", "2025-12-29", 0.300477, 4992, 1500.00),
    ("TAR", "Ak Portföy Tarım ve Gıda Teknolojileri Değişken Fon", "2025-12-29", 2.068742, 362, 750.00),
    ("TMZ", "İş Portföy Sürdürülebilirlik ve Tarım Fon Sepeti Fonu", "2025-12-29", 1.621241, 462, 750.00),
    ("YDI", "Yapıkredi Portföy İkinci Hisse Senedi Fonu", "2025-12-29", 0.361377, 1383, 500.00),
    ("YKT", "Yapı Kredi Portföy Altın Fonu", "2026-01-07", 0.836008, 1196, 1000.00),
    ("YTD", "Yapı Kredi Portföy Yabancı Fon Sepeti Fonu", "2026-01-07", 0.794102, 1259, 1000.00),
    ("AIS", "Ak Portföy Para Piyasası Katılım Fonu", "2026-01-07", 0.084634, 11815, 1000.00),
    ("GUH", "Garanti Portföy Yabancı Teknoloji Hisse Senedi Fonu", "2026-01-07", 0.319714, 3127, 1000.00),
    ("AFT", "Ak Portföy Yeni Teknolojiler Yabancı Hisse Senedi Fonu", "2026-01-07", 0.872769, 1145, 1000.00),
    ("AFA", "Ak Portföy Amerika Yabancı Hisse Senedi Fonu", "2026-01-07", 1.017572, 982, 1000.00),
    ("TAU", "İş Portföy Bist Banka Endeksi Hisse Senedi (TL) Fonu", "2026-01-07", 0.669646, 1493, 1000.00),
    ("TGE", "İş Portföy Emtia Yabancı BYF Fon Sepeti Fonu", "2026-01-07", 0.224431, 4455, 1000.00),
    ("TTE", "Bist Teknoloji Ağırlık Sınırlamalı Endeksi Hisse Senedi (TL) Fonu", "2026-01-07", 1.050217, 966, 1015.00),
    ("ICZ", "Ak Portföy Teknoloji Şirketleri Hisse Senedi Fonu", "2026-01-07", 6.254583, 159, 995.00),
    ("DTZ", "Ak Portföy Robotik Teknolojiler Değişken Fon", "2026-01-07", 4.063723, 246, 1000.00),
    ("MTV", "Ak Portföy Metaverse ve Dijital Yaşam Teknolojileri Fon", "2026-01-07", 4.430463, 225, 1000.00),
    ("AOY", "Ak Portföy Alternatif Enerji Yabancı Hisse Senedi Fonu", "2026-01-07", 0.318135, 3143, 1000.00),
    ("AFS", "Ak Portföy Sağlık Sektörü Yabancı Hisse Senedi Fonu", "2026-01-07", 0.300641, 3326, 1000.00),
    ("TAR", "Ak Portföy Tarım ve Gıda Teknolojileri Değişken Fon", "2026-01-07", 2.107106, 474, 1000.00),
    ("TMZ", "İş Portföy Sürdürülebilirlik ve Tarım Fon Sepeti Fonu", "2026-01-07", 1.639699, 609, 1000.00),
    ("YDI", "Yapıkredi Portföy İkinci Hisse Senedi Fonu", "2026-01-07", 0.407876, 2451, 1000.00),
]

HISSE_ALIMLARI = [
    ("TERA", "Tera Yatırım Menkul Değerler", "2026-01-08", 148.3, 7, 1038.10),
    ("MARMR", "Marmara Holding A.Ş", "2026-01-21", 2.92, 312, 911.04),
    ("SARAE", "Şa-Ra Enerji", "2026-07-09", 70.0, 61, 4270.00),
    ("MASFN", "Masfen Enerji A.Ş", "2026-07-24", 45.68, 81, 3700.00),
    ("CITAS", "Citlekçi Mağazacılık Gıda A.Ş", "2026-08-13", 73.7, 17, 1252.90),
]


# ------------------------------------------------------------------------------
# ALIMLARI KOD BAZINDA TOPLA (aynı fon/hisse birden fazla kez alınmış olabilir)
# ------------------------------------------------------------------------------
def alimlari_topla(alimlar: list) -> dict:
    toplu = {}
    for kod, ad, tarih, fiyat, lot, tutar in alimlar:
        if kod not in toplu:
            toplu[kod] = {"kod": kod, "ad": ad, "toplam_lot": 0, "toplam_tutar": 0.0, "son_fiyat": fiyat, "son_tarih": tarih}
        toplu[kod]["toplam_lot"] += lot
        toplu[kod]["toplam_tutar"] += tutar
        if tarih >= toplu[kod]["son_tarih"]:
            toplu[kod]["son_fiyat"] = fiyat
            toplu[kod]["son_tarih"] = tarih
    for rec in toplu.values():
        rec["ortalama_maliyet"] = rec["toplam_tutar"] / rec["toplam_lot"] if rec["toplam_lot"] else 0.0
    return toplu


fon_toplu = alimlari_topla(FON_ALIMLARI)
hisse_toplu = alimlari_topla(HISSE_ALIMLARI)


# ------------------------------------------------------------------------------
# GÜNCEL FON FİYATLARI — TEFAS resmi API'si, normal yatırım fonları (kind=YAT)
# ------------------------------------------------------------------------------
def yat_fiyatlarini_cek(fon_kodlari: list, gun_sayisi_geriye: int = 7) -> dict:
    crawler = Crawler(timeout=REQUEST_TIMEOUT * 4, max_retry=3)
    for gun_ofset in range(gun_sayisi_geriye):
        tarih = (bugun - timedelta(days=gun_ofset)).strftime("%Y-%m-%d")
        try:
            df = crawler.fetch(tarih, columns="info", kind="YAT")
        except (TefasAPIError, TefasRateLimitError) as e:
            print(f"TEFAS (YAT) API hatası ({tarih}): {e}")
            continue
        except Exception as e:
            print(f"Beklenmeyen hata ({tarih}): {e}")
            continue
        if df is None or df.empty:
            continue
        df_filtreli = df[df["fund_code"].isin(fon_kodlari)]
        if df_filtreli.empty:
            continue
        havuz = {}
        for _, row in df_filtreli.iterrows():
            try:
                havuz[row["fund_code"]] = float(row["price"])
            except (TypeError, ValueError):
                continue
        if havuz:
            print(f"TEFAS (YAT) verisi bulundu: {tarih} ({len(havuz)}/{len(fon_kodlari)} fon)")
            return havuz
    print("TEFAS (YAT): son 7 günde veri bulunamadı, yedek fiyatlara geçildi.")
    return {}


# ------------------------------------------------------------------------------
# GÜNCEL HİSSE FİYATLARI — Yahoo Finance (.IS uzantılı BIST tickerları)
# ------------------------------------------------------------------------------
def hisse_fiyatlarini_cek(hisse_kodlari: list) -> dict:
    if not YFINANCE_VAR:
        print("yfinance kurulu değil, hisse fiyatları yedek değerlerle gösterilecek.")
        return {}
    havuz = {}
    for kod in hisse_kodlari:
        try:
            ticker = yf.Ticker(f"{kod}.IS")
            gecmis = ticker.history(period="5d")
            if gecmis is not None and not gecmis.empty:
                havuz[kod] = float(gecmis["Close"].iloc[-1])
        except Exception as e:
            print(f"{kod} hissesi çekilemedi, yedek fiyat kullanılacak: {e}")
    return havuz


piyasa_fon_havuzu = yat_fiyatlarini_cek(list(fon_toplu.keys()))
piyasa_hisse_havuzu = hisse_fiyatlarini_cek(list(hisse_toplu.keys()))


# ------------------------------------------------------------------------------
# KÂR/ZARAR HESABI
# ------------------------------------------------------------------------------
def kayitlari_hesapla(toplu: dict, piyasa_havuzu: dict) -> list:
    kayitlar = []
    for kod, rec in toplu.items():
        if kod in piyasa_havuzu and piyasa_havuzu[kod] > 0:
            guncel = piyasa_havuzu[kod]
            kaynak = "Canlı"
        else:
            guncel = rec["son_fiyat"]
            kaynak = "Yedek"
        guncel_deger = guncel * rec["toplam_lot"]
        kar = guncel_deger - rec["toplam_tutar"]
        kar_yuzde = (kar / rec["toplam_tutar"] * 100) if rec["toplam_tutar"] else 0.0
        kayitlar.append({
            "kod": kod, "ad": rec["ad"], "lot": rec["toplam_lot"],
            "ortalama_maliyet": rec["ortalama_maliyet"], "guncel_fiyat": guncel,
            "maliyet": rec["toplam_tutar"], "guncel_deger": guncel_deger,
            "kar": kar, "kar_yuzde": kar_yuzde, "kaynak": kaynak,
        })
    kayitlar.sort(key=lambda r: r["kar_yuzde"], reverse=True)
    return kayitlar


fon_kayitlari = kayitlari_hesapla(fon_toplu, piyasa_fon_havuzu)
hisse_kayitlari = kayitlari_hesapla(hisse_toplu, piyasa_hisse_havuzu)

fon_toplam_maliyet = sum(r["maliyet"] for r in fon_kayitlari)
fon_toplam_deger = sum(r["guncel_deger"] for r in fon_kayitlari)
hisse_toplam_maliyet = sum(r["maliyet"] for r in hisse_kayitlari)
hisse_toplam_deger = sum(r["guncel_deger"] for r in hisse_kayitlari)

genel_maliyet = fon_toplam_maliyet + hisse_toplam_maliyet
genel_deger = fon_toplam_deger + hisse_toplam_deger
genel_kar = genel_deger - genel_maliyet
genel_yuzde = (genel_kar / genel_maliyet * 100) if genel_maliyet else 0.0


# ------------------------------------------------------------------------------
# HTML TABLO ÜRETİMİ
# ------------------------------------------------------------------------------
def tablo_satirlari_uret(kayitlar: list, lot_ondalik: int = 0) -> str:
    satirlar = []
    for r in kayitlar:
        renk = "#166534" if r["kar"] >= 0 else "#991b1b"
        isaret = "+" if r["kar"] >= 0 else ""
        kaynak_renk = "#059669" if r["kaynak"] == "Canlı" else "#d97706"
        ad_guvenli = html.escape(r["ad"])
        satirlar.append(f"""
        <tr>
            <td style='padding:12px 14px; border-bottom:1px solid #e2e8f0; font-weight:bold; color:#1e293b;'>{r['kod']}</td>
            <td style='padding:12px 14px; border-bottom:1px solid #e2e8f0; color:#475569; font-size:13px;'>{ad_guvenli}</td>
            <td style='padding:12px 14px; border-bottom:1px solid #e2e8f0; color:#475569;'>{r['lot']:,.{lot_ondalik}f}</td>
            <td style='padding:12px 14px; border-bottom:1px solid #e2e8f0; color:#64748b; font-family:monospace;'>{r['ortalama_maliyet']:.4f}</td>
            <td style='padding:12px 14px; border-bottom:1px solid #e2e8f0; color:#0f172a; font-family:monospace; font-weight:500;'>{r['guncel_fiyat']:.4f} <span style="color:{kaynak_renk}; font-size:10px; font-weight:700;">● {r['kaynak']}</span></td>
            <td style='padding:12px 14px; border-bottom:1px solid #e2e8f0; color:#475569;'>{r['maliyet']:,.2f} TL</td>
            <td style='padding:12px 14px; border-bottom:1px solid #e2e8f0; color:#0f172a; font-weight:500;'>{r['guncel_deger']:,.2f} TL</td>
            <td style='padding:12px 14px; border-bottom:1px solid #e2e8f0; color:{renk}; font-weight:600;'>{isaret}%{r['kar_yuzde']:.2f}</td>
            <td style='padding:12px 14px; border-bottom:1px solid #e2e8f0; font-weight:bold; color:{renk};'>{isaret}{r['kar']:,.2f} TL</td>
        </tr>
        """)
    return "".join(satirlar)


fon_tablo_html = tablo_satirlari_uret(fon_kayitlari)
hisse_tablo_html = tablo_satirlari_uret(hisse_kayitlari)

html_icerik = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <title>Midas Portfoyum</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'unsafe-inline'; img-src 'self' data:;">
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background-color:#f8fafc; margin:0; padding:20px; color:#333;">
    <div style="max-width:1200px; margin:0 auto; background:white; padding:30px; border-radius:16px; box-shadow:0 10px 25px rgba(0,0,0,0.03); border:1px solid #e2e8f0;">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:2px solid #f1f5f9; padding-bottom:20px; margin-bottom:25px; flex-wrap:wrap; gap:15px;">
            <div>
                <h1 style="margin:0; color:#0f172a; font-size:24px; font-weight:800; letter-spacing:-0.5px;">Midas Portföyüm</h1>
                <p style="color:#64748b; font-size:14px; margin:5px 0 0 0;">Yatırım Fonları + BIST Hisseleri · Son Güncelleme: <strong>{tarih_str} - {bugun.strftime('%H:%M')}</strong></p>
            </div>
            <a href="index.html" style="color:#2563eb; text-decoration:none; font-weight:600; font-size:14px; white-space:nowrap;">← BES Portföyüm</a>
        </div>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:20px; margin-bottom:30px;">
            <div style="background:#f8fafc; padding:20px; border-radius:12px; border:1px solid #e2e8f0;">
                <div style="font-size:13px; font-weight:600; color:#64748b; text-transform:uppercase;">Toplam Yatırım</div>
                <div style="font-size:26px; font-weight:800; color:#0f172a; margin-top:8px;">{genel_maliyet:,.2f} TL</div>
            </div>
            <div style="background:#f8fafc; padding:20px; border-radius:12px; border:1px solid #e2e8f0;">
                <div style="font-size:13px; font-weight:600; color:#64748b; text-transform:uppercase;">Güncel Değer</div>
                <div style="font-size:26px; font-weight:800; color:#0f172a; margin-top:8px;">{genel_deger:,.2f} TL</div>
            </div>
            <div style="background:{'#f0fdf4' if genel_kar >= 0 else '#fef2f2'}; padding:20px; border-radius:12px; border:1px solid {'#bbf7d0' if genel_kar >= 0 else '#fecaca'}; border-left:6px solid {'#10b981' if genel_kar >= 0 else '#ef4444'};">
                <div style="font-size:13px; font-weight:600; color:{'#15803d' if genel_kar >= 0 else '#b91c1c'}; text-transform:uppercase;">Net Kâr/Zarar</div>
                <div style="font-size:26px; font-weight:800; color:{'#166534' if genel_kar >= 0 else '#991b1b'}; margin-top:8px;">{'+' if genel_kar >= 0 else ''}{genel_kar:,.2f} TL</div>
            </div>
            <div style="background:#f0fdfa; padding:20px; border-radius:12px; border:1px solid #99f6e4;">
                <div style="font-size:13px; font-weight:600; color:#0f766e; text-transform:uppercase;">Toplam Getiri</div>
                <div style="font-size:26px; font-weight:800; color:#115e59; margin-top:8px;">{'+' if genel_yuzde >= 0 else ''}%{genel_yuzde:.2f}</div>
            </div>
        </div>

        <h3 style="color:#1e293b; font-size:16px; margin-bottom:10px;">📁 Yatırım Fonları <span style="font-weight:400; color:#94a3b8; font-size:12px;">({len(fon_kayitlari)} fon · {fon_toplam_maliyet:,.2f} TL)</span></h3>
        <div style="overflow-x:auto; margin-bottom:30px; border:1px solid #e2e8f0; border-radius:12px;">
            <table style="width:100%; border-collapse:collapse; text-align:left; font-size:13.5px;">
                <thead>
                    <tr style="background:#1e293b; color:white; font-weight:600;">
                        <th style="padding:12px 14px;">Kod</th><th style="padding:12px 14px;">Fon Adı</th>
                        <th style="padding:12px 14px;">Lot</th><th style="padding:12px 14px;">Ort. Maliyet</th>
                        <th style="padding:12px 14px;">Güncel Fiyat</th><th style="padding:12px 14px;">Maliyet</th>
                        <th style="padding:12px 14px;">Güncel Değer</th><th style="padding:12px 14px;">Getiri</th>
                        <th style="padding:12px 14px;">Kâr/Zarar</th>
                    </tr>
                </thead>
                <tbody>{fon_tablo_html}</tbody>
            </table>
        </div>

        <h3 style="color:#1e293b; font-size:16px; margin-bottom:10px;">📈 Hisse Senetleri <span style="font-weight:400; color:#94a3b8; font-size:12px;">({len(hisse_kayitlari)} hisse · {hisse_toplam_maliyet:,.2f} TL)</span></h3>
        <div style="overflow-x:auto; margin-bottom:10px; border:1px solid #e2e8f0; border-radius:12px;">
            <table style="width:100%; border-collapse:collapse; text-align:left; font-size:13.5px;">
                <thead>
                    <tr style="background:#1e293b; color:white; font-weight:600;">
                        <th style="padding:12px 14px;">Kod</th><th style="padding:12px 14px;">Şirket</th>
                        <th style="padding:12px 14px;">Lot</th><th style="padding:12px 14px;">Ort. Maliyet</th>
                        <th style="padding:12px 14px;">Güncel Fiyat</th><th style="padding:12px 14px;">Maliyet</th>
                        <th style="padding:12px 14px;">Güncel Değer</th><th style="padding:12px 14px;">Getiri</th>
                        <th style="padding:12px 14px;">Kâr/Zarar</th>
                    </tr>
                </thead>
                <tbody>{hisse_tablo_html}</tbody>
            </table>
        </div>

        <p style="color:#94a3b8; font-size:11.5px; margin-top:20px;">
            Fon fiyatları TEFAS resmi API'sinden (pytefas, kind=YAT), hisse fiyatları Yahoo Finance'ten (.IS) çekilir.
            Erişilemediğinde en son bilinen alım fiyatı "Yedek" etiketiyle gösterilir. Bu sayfa BES emeklilik
            takip panelinden tamamen bağımsızdır, ayrı hesaplanır.
        </p>
    </div>
</body>
</html>
"""

os.makedirs("public", exist_ok=True)
with open("public/midas.html", "w", encoding="utf-8") as f:
    f.write(html_icerik)

print("Midas paneli güncellendi.")
print(f"Fon kaynağı: {'canlı' if piyasa_fon_havuzu else 'yedek'} | Hisse kaynağı: {'canlı' if piyasa_hisse_havuzu else 'yedek'}")
