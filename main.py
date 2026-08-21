import os
import ssl
import json
import html
import urllib.request
import urllib.parse
import statistics
from datetime import datetime, timedelta

import pandas as pd
from pytefas import Crawler, TefasAPIError, TefasRateLimitError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ==============================================================================
# AYARLAR
# ==============================================================================
aylik_odeme = 5000.0
baslangic_tarihi = datetime(2026, 8, 5)
bugun = datetime.now()

# Manuel varsayım — TCMB_API_KEY tanımlı değilse veya erişim başarısız olursa
# bu sabit değer kullanılır (yedek). Aksi halde aşağıdaki fonksiyon gerçek
# TÜFE'yi otomatik çeker ve bu değerin yerini alır.
AYLIK_ENFLASYON_VARSAYIMI = 3.0  # % — sadece TCMB erişilemezse kullanılır

# Uyarı eşiği: toplam değişim bu yüzdeyi (mutlak) aşarsa webhook'a bildirim gider.
BILDIRIM_ESIK = 5.0

# Hassas değerler koda YAZILMAZ — GitHub Actions Secrets üzerinden okunur.
# Repo Settings > Secrets and variables > Actions altından tanımlayın:
#   ALERT_WEBHOOK_URL  -> Telegram/Slack webhook (opsiyonel)
#   TCMB_API_KEY       -> evds2.tcmb.gov.tr'den ücretsiz alınan EVDS API anahtarı (opsiyonel)
WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
TCMB_API_KEY = os.environ.get("TCMB_API_KEY", "").strip()

MAX_RESPONSE_BYTES = 200_000  # kötü niyetli/aşırı büyük yanıta karşı üst sınır
REQUEST_TIMEOUT = 5

HISTORY_PATH = "data/history.json"  # repo içinde kalıcı, workflow'da commit edilmeli

ay_sayisi = (bugun.year - baslangic_tarihi.year) * 12 + (bugun.month - baslangic_tarihi.month) + 1
if bugun.day < baslangic_tarihi.day and ay_sayisi > 1:
    ay_sayisi -= 1

toplam_anapara = float(aylik_odeme * ay_sayisi)

fon_tanimlari = {
    'GEL': {'ad': 'Para Piyasası Emeklilik Yatırım Fonu', 'agirlik': 0.20, 'giris_fiyati': 0.436406},
    'GEH': {'ad': 'Hisse Senedi Emeklilik Yatırım Fonu', 'agirlik': 0.30, 'giris_fiyati': 2.779911},
    'EMY': {'ad': 'Altın Emeklilik Yatırım Fonu', 'agirlik': 0.20, 'giris_fiyati': 0.009987},
    'GHG': {'ad': 'Dış Borçlanma Araçları Emeklilik Yatırım Fonu', 'agirlik': 0.20, 'giris_fiyati': 1.201487},
    'GHH': {'ad': 'Sürdürülebilirlik Hisse Senedi Emeklilik Yatırım Fonu', 'agirlik': 0.10, 'giris_fiyati': 0.395887},
}

# Fallback fiyatları 6 ondalığa çıkarıldı — EMY/GEL gibi düşük birim fiyatlı
# fonlarda 4 ondalık gerçek kârı gizliyordu (örn. EMY 0.0103 vs gerçek 0.010863).
YEDEK_FIYATLAR = {
    'GEL': 0.442970, 'GEH': 2.833800, 'EMY': 0.010863, 'GHG': 1.215962, 'GHH': 0.400294,
}

tarih_str = bugun.strftime('%d-%m-%Y')
tarih_iso = bugun.strftime('%Y-%m-%d')


# ------------------------------------------------------------------------------
# GERÇEK VERİ ÇEKME — TEFAS resmi API'si (pytefas)
# ------------------------------------------------------------------------------
FON_KODLARI = list(fon_tanimlari.keys())


def tefas_fiyatlarini_cek(fon_kodlari: list, gun_sayisi_geriye: int = 7) -> dict:
    """TEFAS'ın resmi API'sinden (tefas.gov.tr/api/funds/...) emeklilik
    fonu (EMK) fiyatlarını çeker. Bugünden geriye doğru en fazla
    `gun_sayisi_geriye` gün tarar — TEFAS hafta sonu/tatilde veri
    yayınlamadığı için en son yayınlanan iş günü fiyatını bulur.
    Herhangi bir hata durumunda boş dict döner; Action bu yüzden çökmez,
    çağıran taraf YEDEK_FIYATLAR'a düşer."""
    crawler = Crawler(timeout=REQUEST_TIMEOUT * 4, max_retry=3)

    for gun_ofset in range(gun_sayisi_geriye):
        tarih = (bugun - timedelta(days=gun_ofset)).strftime("%Y-%m-%d")
        try:
            df = crawler.fetch(tarih, columns="info", kind="EMK")
        except (TefasAPIError, TefasRateLimitError) as e:
            print(f"TEFAS API hatası ({tarih}): {e}")
            continue
        except Exception as e:
            print(f"Beklenmeyen hata ({tarih}): {e}")
            continue

        if df is None or df.empty:
            continue  # o gün veri yok (hafta sonu/tatil) -> bir önceki güne bak

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
            print(f"TEFAS verisi bulundu: {tarih} ({len(havuz)}/{len(fon_kodlari)} fon)")
            return havuz

    print("Son 7 günde TEFAS verisi bulunamadı, yedek fiyatlara geçildi.")
    return {}


try:
    piyasa_havuzu = tefas_fiyatlarini_cek(FON_KODLARI)
except Exception as e:
    print(f"TEFAS entegrasyonu tamamen başarısız oldu, yedek fiyatlara geçildi: {e}")
    piyasa_havuzu = {}

# ------------------------------------------------------------------------------
# GEÇMİŞ VERİ (TARİHSEL GRAFİK + RİSK METRİKLERİ İÇİN)
# ------------------------------------------------------------------------------
def gecmisi_yukle(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def gecmisi_kaydet(path: str, gecmis: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(gecmis, f, ensure_ascii=False, indent=2)


gecmis = gecmisi_yukle(HISTORY_PATH)

# ------------------------------------------------------------------------------
# FON HESAPLAMALARI
# ------------------------------------------------------------------------------
rapor_data = []
grafik_cubuklari_html = []
fon_kayitlari = []  # CSV + PDF için ortak, tek seferde hesaplanmış veri
renkler = ['#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6']

toplam_maliyet = 0.0
toplam_guncel_deger = 0.0

for idx, (kod, info) in enumerate(fon_tanimlari.items()):
    giris_fiy = float(info['giris_fiyati'])

    if kod in piyasa_havuzu and piyasa_havuzu[kod] > 0:
        guncel_fiy = piyasa_havuzu[kod]
        kaynak_etiket = '<span style="color:#059669;font-size:11px;font-weight:600;">● Canlı</span>'
    else:
        guncel_fiy = float(YEDEK_FIYATLAR.get(kod, giris_fiy))
        kaynak_etiket = '<span style="color:#d97706;font-size:11px;font-weight:600;">● Yedek</span>'

    toplam_degisim_orani = ((guncel_fiy - giris_fiy) / giris_fiy) * 100
    fon_maliyeti = toplam_anapara * info['agirlik']
    fon_guncel_degeri = fon_maliyeti * (1 + (toplam_degisim_orani / 100))
    fon_net_kar_zarar = fon_guncel_degeri - fon_maliyeti

    toplam_maliyet += fon_maliyeti
    toplam_guncel_deger += fon_guncel_degeri

    fon_kayitlari.append({
        "kod": kod, "ad": info['ad'], "agirlik": info['agirlik'] * 100,
        "maliyet": fon_maliyeti, "giris": giris_fiy, "guncel": guncel_fiy,
        "degisim": toplam_degisim_orani, "kar": fon_net_kar_zarar,
        "pay_sayisi": fon_maliyeti / giris_fiy,
        "kaynak": "Canlı" if kod in piyasa_havuzu and piyasa_havuzu[kod] > 0 else "Yedek",
    })

    arti_eksi = "+" if fon_net_kar_zarar >= 0 else ""

    bar_height = max(5, min(int(abs(fon_net_kar_zarar) * 2), 200))
    grafik_cubuklari_html.append(f"""
    <div style="display:flex; flex-direction:column; align-items:center; flex:1; min-width:60px;">
        <div style="font-size:11px; font-weight:bold; margin-bottom:5px; color:#1e293b;">{arti_eksi}{fon_net_kar_zarar:.2f} TL</div>
        <div style="width:100%; background-color:{renkler[idx % len(renkler)]}; height:{bar_height}px; border-radius:6px 6px 0 0;"></div>
        <div style="margin-top:8px; font-weight:bold; font-size:13px; color:#475569;">{kod}</div>
    </div>
    """)

genel_kar = toplam_guncel_deger - toplam_maliyet
dogru_genel_degisim = (genel_kar / toplam_maliyet) * 100 if toplam_maliyet else 0.0

# ------------------------------------------------------------------------------
# GEÇMİŞE BUGÜNÜ EKLE (aynı gün varsa güncelle, yoksa ekle)
# Artık fon bazlı fiyatlar da kaydediliyor -> her fonun günlük değişimi
# hesaplanabiliyor (aşağıda).
# ------------------------------------------------------------------------------
bugun_kaydi = {
    "tarih": tarih_iso,
    "toplam_deger": round(toplam_guncel_deger, 2),
    "toplam_kar": round(genel_kar, 2),
    "toplam_degisim": round(dogru_genel_degisim, 4),
    "fonlar": {r["kod"]: r["guncel"] for r in fon_kayitlari},
}
gecmis = [g for g in gecmis if g.get("tarih") != tarih_iso]
gecmis.append(bugun_kaydi)
gecmis.sort(key=lambda g: g["tarih"])
gecmisi_kaydet(HISTORY_PATH, gecmis)

# ------------------------------------------------------------------------------
# FON BAZLI GÜNLÜK KÂR/ZARAR — bir önceki günün kayıtlı fon fiyatına göre
# ------------------------------------------------------------------------------
fon_gunluk = {}
if len(gecmis) >= 2 and "fonlar" in gecmis[-2]:
    dunku_fonlar = gecmis[-2]["fonlar"]
    for r in fon_kayitlari:
        dunku_fiyat = dunku_fonlar.get(r["kod"])
        if dunku_fiyat:
            fark_fiyat = r["guncel"] - dunku_fiyat
            fon_gunluk[r["kod"]] = {
                "tl": fark_fiyat * r["pay_sayisi"],
                "yuzde": (fark_fiyat / dunku_fiyat) * 100,
            }

# ------------------------------------------------------------------------------
# FON TABLOSU SATIRLARI — günlük değişim dahil, tüm veri hazır olduktan sonra üretilir
# ------------------------------------------------------------------------------
for r in fon_kayitlari:
    renk = "green" if r["kar"] >= 0 else "red"
    arti_eksi = "+" if r["kar"] >= 0 else ""
    ad_guvenli = html.escape(r["ad"])
    kaynak_etiket = (
        '<span style="color:#059669;font-size:11px;font-weight:600;">● Canlı</span>'
        if r["kaynak"] == "Canlı" else
        '<span style="color:#d97706;font-size:11px;font-weight:600;">● Yedek</span>'
    )

    gunluk = fon_gunluk.get(r["kod"])
    if gunluk is None:
        gunluk_html = '<span style="color:#94a3b8; font-size:12px;">İlk gün</span>'
    else:
        g_renk = "#059669" if gunluk["tl"] >= 0 else "#dc2626"
        g_isaret = "+" if gunluk["tl"] >= 0 else ""
        gunluk_html = (
            f'<span style="color:{g_renk}; font-weight:600;">{g_isaret}{gunluk["tl"]:.2f} TL</span>'
            f'<br><span style="color:{g_renk}; font-size:11px;">({g_isaret}%{gunluk["yuzde"]:.2f})</span>'
        )

    rapor_data.append(f"""
    <tr>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; font-weight:bold; color:#1e293b;'>{r['kod']}</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#475569;'>{ad_guvenli}</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#475569; font-weight:500;'>{r['agirlik']:.1f}%</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#475569;'>{r['maliyet']:.2f} TL</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#64748b; font-family:monospace;'>{r['giris']:.6f} TL</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#0f172a; font-family:monospace; font-weight:500;'>{r['guncel']:.6f} TL {kaynak_etiket}</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:{renk}; font-weight:600;'>{arti_eksi}{r['degisim']:.2f}%</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; text-align:center;'>{gunluk_html}</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; font-weight:bold; color:{renk};'>{arti_eksi}{r['kar']:.2f} TL</td>
    </tr>
    """)

# ------------------------------------------------------------------------------
# GÜNLÜK KÂR/ZARAR — bir önceki güne kayıtlı toplam değere göre (history.json)
# ------------------------------------------------------------------------------
gunluk_kar_html = '<div style="font-size:11px; color:#a16207; margin-top:6px;">İlk gün — kıyaslanacak dünkü veri yok</div>'
if len(gecmis) >= 2:
    dunku_deger = gecmis[-2]["toplam_deger"]
    gunluk_fark = toplam_guncel_deger - dunku_deger
    gunluk_yuzde = (gunluk_fark / dunku_deger * 100) if dunku_deger else 0.0
    g_renk = "#059669" if gunluk_fark >= 0 else "#dc2626"
    g_isaret = "+" if gunluk_fark >= 0 else ""
    gunluk_kar_html = (
        f'<div style="display:inline-flex; align-items:center; gap:4px; margin-top:6px; '
        f'background:{g_renk}1a; color:{g_renk}; font-size:12px; font-weight:700; '
        f'padding:3px 8px; border-radius:999px;">Bugün: {g_isaret}{gunluk_fark:.2f} TL ({g_isaret}%{gunluk_yuzde:.2f})</div>'
    )

# ------------------------------------------------------------------------------
# RİSK METRİKLERİ (geçmişten)
# ------------------------------------------------------------------------------
volatilite_html = "Yetersiz veri (en az 2 gün gerekli)"
drawdown_html = "Yetersiz veri"
if len(gecmis) >= 2:
    degerler = [g["toplam_deger"] for g in gecmis]
    gunluk_getiriler = [
        (degerler[i] - degerler[i - 1]) / degerler[i - 1] * 100
        for i in range(1, len(degerler)) if degerler[i - 1] != 0
    ]
    if len(gunluk_getiriler) >= 2:
        volatilite = statistics.stdev(gunluk_getiriler)
        volatilite_html = f"%{volatilite:.2f} (günlük std. sapma)"
    zirve = degerler[0]
    maks_dusus = 0.0
    for v in degerler:
        zirve = max(zirve, v)
        dusus = (v - zirve) / zirve * 100 if zirve else 0
        maks_dusus = min(maks_dusus, dusus)
    drawdown_html = f"%{maks_dusus:.2f}"

# ------------------------------------------------------------------------------
# DÖNEMSEL GETİRİLER — SADECE SİTENİN KENDİ history.json VERİSİNDEN
# (dışarıdan hiçbir kaynak çekilmez; veri, panelin kendi takip başlangıcından
# bu yana biriktirdiği günlük kayıtlara dayanır)
# ------------------------------------------------------------------------------
def donem_getirisi_hesapla(gecmis: list, gun: int):
    """`gun` kadar gün öncesine ait en yakın (aynı veya önceki) kaydı bulup
    bugüne kadarki % değişimi döner. Geçmiş o kadar geriye gitmiyorsa None
    döner -> arayüzde 'Yetersiz veri' gösterilir, asla sahte 0.00 yazılmaz."""
    if len(gecmis) < 2:
        return None
    hedef_tarih = bugun - timedelta(days=gun)
    en_eski_tarih = datetime.strptime(gecmis[0]["tarih"], "%Y-%m-%d")
    if en_eski_tarih > hedef_tarih:
        return None

    baslangic_kaydi = None
    for g in gecmis:
        g_tarih = datetime.strptime(g["tarih"], "%Y-%m-%d")
        if g_tarih <= hedef_tarih:
            baslangic_kaydi = g
        else:
            break
    if baslangic_kaydi is None:
        return None

    baslangic_deger = baslangic_kaydi["toplam_deger"]
    bitis_deger = gecmis[-1]["toplam_deger"]
    if baslangic_deger == 0:
        return None
    return (bitis_deger - baslangic_deger) / baslangic_deger * 100


DONEM_TANIMLARI = [
    ("Son 1 Hafta", 7), ("Son 1 Ay", 30), ("Son 3 Ay", 90),
    ("Son 6 Ay", 180), ("Son 1 Yıl", 365),
]

donem_kartlari_html = []
for etiket, gun in DONEM_TANIMLARI:
    getiri = donem_getirisi_hesapla(gecmis, gun)
    if getiri is None:
        deger_html = '<span style="font-size:15px; color:#94a3b8; font-weight:600;">Yetersiz veri</span>'
    else:
        renk = "#059669" if getiri >= 0 else "#dc2626"
        deger_html = f'<span style="font-size:22px; font-weight:800; color:{renk};">%{getiri:+.2f}</span>'
    donem_kartlari_html.append(f"""
    <div style="flex:1; min-width:130px; background:#f8fafc; border:1px solid #e2e8f0; border-top:3px solid #14b8a6; border-radius:10px; padding:14px; text-align:center;">
        <div style="font-size:11px; font-weight:600; color:#64748b; text-transform:uppercase; margin-bottom:8px;">{etiket}</div>
        {deger_html}
    </div>
    """)
donem_kartlari_html = "".join(donem_kartlari_html)

# ------------------------------------------------------------------------------
# FON DAĞILIM GRAFİĞİ (DONUT) — SAF SVG, fon_kayitlari'ndan otomatik üretilir.
# Fon sayısı artınca (fon_tanimlari sözlüğüne yeni fon eklenince) hem grafik
# hem lejant otomatik genişler, kod değişikliği gerekmez.
# ------------------------------------------------------------------------------
RENK_PALETI = ['#f59e0b', '#8b5cf6', '#2dd4bf', '#f472b6', '#38bdf8',
               '#4ade80', '#fb7185', '#a78bfa', '#facc15', '#f97316']
fon_renkleri = {r["kod"]: RENK_PALETI[i % len(RENK_PALETI)] for i, r in enumerate(fon_kayitlari)}


def svg_donut_grafik(fon_kayitlari: list, renk_map: dict, boyut=220, kalinlik=34) -> str:
    r = (boyut - kalinlik) / 2
    cx = cy = boyut / 2
    cevre = 2 * 3.14159265 * r
    cumulatif = 0.0
    parcalar = []
    for rec in fon_kayitlari:
        oran = rec["agirlik"] / 100
        dash = oran * cevre
        offset = -cumulatif * cevre
        parcalar.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{renk_map[rec["kod"]]}" '
            f'stroke-width="{kalinlik}" stroke-dasharray="{dash:.2f} {cevre - dash:.2f}" '
            f'stroke-dashoffset="{offset:.2f}" transform="rotate(-90 {cx} {cy})"></circle>'
        )
        cumulatif += oran

    return f"""
    <svg viewBox="0 0 {boyut} {boyut}" style="width:180px; height:180px; flex-shrink:0;">
        {"".join(parcalar)}
        <text x="{cx}" y="{cy - 4}" text-anchor="middle" font-size="20" font-weight="800" fill="#0f172a">{len(fon_kayitlari)}</text>
        <text x="{cx}" y="{cy + 14}" text-anchor="middle" font-size="10" fill="#94a3b8">FON</text>
    </svg>
    """


donut_svg = svg_donut_grafik(fon_kayitlari, fon_renkleri)
lejant_html = "".join(f"""
    <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
        <span style="width:11px; height:11px; border-radius:3px; background:{fon_renkleri[r['kod']]}; flex-shrink:0;"></span>
        <span style="font-size:12.5px; color:#334155; font-weight:600;">{r['kod']}</span>
        <span style="font-size:12px; color:#94a3b8; margin-left:auto;">%{r['agirlik']:.1f}</span>
    </div>
""" for r in fon_kayitlari)

# ------------------------------------------------------------------------------
# ENFLASYON KARŞILAŞTIRMA — TCMB EVDS resmi API'si (TP.FG.J0, TÜFE Genel Endeks)
# ------------------------------------------------------------------------------
def tufe_kumulatif_getir(api_key: str, baslangic: datetime, bitis: datetime):
    """TCMB EVDS'den TÜFE genel endeksini (TP.FG.J0) aylık düzeyde çeker,
    dönem başı ve son yayınlanan ay arasındaki gerçek kümülatif % değişimi
    döner. Hata/anahtar yoksa None döner -> çağıran taraf manuel varsayıma düşer."""
    if not api_key:
        return None
    try:
        params = urllib.parse.urlencode({
            "series": "TP.FG.J0",
            "startDate": baslangic.strftime("%d-%m-%Y"),
            "endDate": bitis.strftime("%d-%m-%Y"),
            "frequency": "5",  # aylık
            "type": "json",
        })
        url = f"https://evds2.tcmb.gov.tr/service/evds/{params}"
        req = urllib.request.Request(url, headers={"key": api_key})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT * 2, context=ctx) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                print("TCMB EVDS: yanıt boyut sınırını aştı, reddedildi.")
                return None
            data = json.loads(raw.decode("utf-8"))

        items = data.get("items", [])
        if not items:
            return None

        degerler = []
        for item in items:
            v = item.get("TP_FG_J0")
            if v is None:
                continue
            try:
                degerler.append(float(v))
            except (TypeError, ValueError):
                continue

        if len(degerler) < 2:
            return None

        ilk, son = degerler[0], degerler[-1]
        if ilk <= 0:
            return None
        return (son - ilk) / ilk * 100
    except Exception as e:
        print(f"TCMB EVDS erişilemedi, manuel TÜFE varsayımına geçildi: {e}")
        return None


tahmini_enflasyon = tufe_kumulatif_getir(TCMB_API_KEY, baslangic_tarihi, bugun)
if tahmini_enflasyon is not None:
    enflasyon_kaynagi = "TCMB EVDS (gerçek, kümülatif)"
    print(f"TÜFE otomatik çekildi: %{tahmini_enflasyon:.2f} (dönem toplamı)")
else:
    tahmini_enflasyon = AYLIK_ENFLASYON_VARSAYIMI * ay_sayisi
    enflasyon_kaynagi = "manuel varsayım"
    print("TÜFE otomatik çekilemedi, manuel varsayım kullanıldı.")

enflasyon_farki = dogru_genel_degisim - tahmini_enflasyon
enf_renk = "#059669" if enflasyon_farki >= 0 else "#dc2626"
enf_yon = "üzerinde" if enflasyon_farki >= 0 else "altında"

# ------------------------------------------------------------------------------
# TARİHSEL GRAFİK — SAF SVG (harici JS/CDN yok, sıfır ek yükleme gecikmesi)
# ------------------------------------------------------------------------------
def svg_cizgi_grafik(gecmis: list, genislik=640, yukseklik=140) -> str:
    if len(gecmis) < 2:
        return '<p style="color:#94a3b8;font-size:13px;">Grafik için en az 2 günlük veri gerekli. Yarın tekrar kontrol edin.</p>'

    degerler = [g["toplam_deger"] for g in gecmis]
    min_v, max_v = min(degerler), max(degerler)
    span = (max_v - min_v) or 1
    pad = 10
    n = len(degerler)

    noktalar = []
    for i, v in enumerate(degerler):
        x = pad + (i / (n - 1)) * (genislik - 2 * pad)
        y = yukseklik - pad - ((v - min_v) / span) * (yukseklik - 2 * pad)
        noktalar.append((round(x, 1), round(y, 1)))

    cizgi = " ".join(f"{x},{y}" for x, y in noktalar)
    renk = "#10b981" if degerler[-1] >= degerler[0] else "#dc2626"
    dolgu_noktalari = f"{pad},{yukseklik - pad} " + cizgi + f" {genislik - pad},{yukseklik - pad}"

    ilk_etiket = html.escape(gecmis[0]["tarih"])
    son_etiket = html.escape(gecmis[-1]["tarih"])

    return f"""
    <svg viewBox="0 0 {genislik} {yukseklik}" style="width:100%; height:auto;" preserveAspectRatio="none">
        <polygon points="{dolgu_noktalari}" fill="{renk}" opacity="0.08"></polygon>
        <polyline points="{cizgi}" fill="none" stroke="{renk}" stroke-width="2.5"
                   stroke-linejoin="round" stroke-linecap="round"></polyline>
    </svg>
    <div style="display:flex; justify-content:space-between; font-size:11px; color:#94a3b8; margin-top:4px;">
        <span>{ilk_etiket}</span><span>{son_etiket}</span>
    </div>
    """


tarihsel_grafik_svg = svg_cizgi_grafik(gecmis)

# ------------------------------------------------------------------------------
# KATKI PAYI TAKVİMİ
# ------------------------------------------------------------------------------
katki_chips = []
yil, ay = baslangic_tarihi.year, baslangic_tarihi.month
for i in range(ay_sayisi):
    etiket = f"{ay:02d}.{yil}"
    katki_chips.append(
        f'<span style="display:inline-block;background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;'
        f'border-radius:8px;padding:4px 10px;font-size:11px;font-weight:600;margin:2px;">✓ {etiket} · {aylik_odeme:.0f} TL</span>'
    )
    ay += 1
    if ay > 12:
        ay = 1
        yil += 1
katki_html = "".join(katki_chips)

# ------------------------------------------------------------------------------
# CSV EXPORT — Türkçe Excel uyumlu (virgül hem ondalık hem ayraç çakışması
# nedeniyle "sep=," direktifiyle Excel'e doğru ayraç bildiriliyor)
# ------------------------------------------------------------------------------
os.makedirs("public", exist_ok=True)
csv_df = pd.DataFrame([{
    "Fon Kodu": r["kod"], "Fon Adı": r["ad"], "Ağırlık(%)": round(r["agirlik"], 1),
    "Maliyet(TL)": round(r["maliyet"], 2), "Giriş Fiyatı": round(r["giris"], 6),
    "Güncel Fiyat": round(r["guncel"], 6), "Değişim(%)": round(r["degisim"], 2),
    "Net Kâr/Zarar(TL)": round(r["kar"], 2), "Kaynak": r["kaynak"],
} for r in fon_kayitlari])
with open("public/portfoy_raporu.csv", "w", encoding="utf-8-sig", newline="") as f:
    f.write("sep=,\n")
    csv_df.to_csv(f, index=False)

# ------------------------------------------------------------------------------
# PDF EXPORT — reportlab (saf Python, sistem kütüphanesi gerekmez),
# sitedeki tabloyla aynı veri ve renk şeması
# ------------------------------------------------------------------------------
def pdf_raporu_uret(yol: str):
    doc = SimpleDocTemplate(
        yol, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    baslik_stili = ParagraphStyle("Baslik", parent=styles["Title"], fontSize=17,
                                   textColor=colors.HexColor("#0f172a"), spaceAfter=2)
    alt_baslik_stili = ParagraphStyle("AltBaslik", parent=styles["Normal"], fontSize=9.5,
                                       textColor=colors.HexColor("#64748b"), spaceAfter=14)
    bolum_stili = ParagraphStyle("Bolum", parent=styles["Heading2"], fontSize=12,
                                  textColor=colors.HexColor("#1e293b"), spaceBefore=14, spaceAfter=6)

    story = [
        Paragraph("Garanti BES Portföy Takip Raporu", baslik_stili),
        Paragraph(f"Oluşturulma: {tarih_str} - {bugun.strftime('%H:%M')}", alt_baslik_stili),
    ]

    # Özet kutuları
    ozet_veri = [
        ["Yatırılan Anapara", "Net Kâr", "Portföy Büyümesi", "Enflasyona Göre"],
        [f"{toplam_maliyet:.2f} TL", f"+{genel_kar:.2f} TL",
         f"+%{dogru_genel_degisim:.2f}", f"%{enflasyon_farki:+.2f} {enf_yon}"],
    ]
    ozet_tablo = Table(ozet_veri, colWidths=[42 * mm] * 4)
    ozet_tablo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f8fafc")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#64748b")),
        ("TEXTCOLOR", (1, 1), (1, 1), colors.HexColor("#166534")),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 12),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))
    story.append(ozet_tablo)
    story.append(Paragraph(f"Dönem: {ay_sayisi}. Ay &nbsp;·&nbsp; Kaynak: {enflasyon_kaynagi}", alt_baslik_stili))

    # Fon tablosu
    story.append(Paragraph("Fon Bazlı Detay", bolum_stili))
    tablo_basliklari = ["Kod", "Ağırlık", "Maliyet", "Giriş", "Güncel", "Değişim", "Kâr/Zarar", "Kaynak"]
    tablo_satirlari = [tablo_basliklari]
    for r in fon_kayitlari:
        tablo_satirlari.append([
            r["kod"], f"%{r['agirlik']:.1f}", f"{r['maliyet']:.2f} TL",
            f"{r['giris']:.6f}", f"{r['guncel']:.6f}", f"%{r['degisim']:+.2f}",
            f"{r['kar']:+.2f} TL", r["kaynak"],
        ])

    fon_tablo = Table(tablo_satirlari, colWidths=[16 * mm, 16 * mm, 22 * mm, 24 * mm, 24 * mm, 20 * mm, 24 * mm, 18 * mm])
    tablo_stil = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]
    for i, r in enumerate(fon_kayitlari, start=1):
        renk_hex = "#166534" if r["kar"] >= 0 else "#991b1b"
        tablo_stil.append(("TEXTCOLOR", (6, i), (6, i), colors.HexColor(renk_hex)))
        tablo_stil.append(("FONTNAME", (6, i), (6, i), "Helvetica-Bold"))
    fon_tablo.setStyle(TableStyle(tablo_stil))
    story.append(fon_tablo)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Bu rapor otomatik oluşturulmuştur. Fiyatlar TEFAS resmi API'sinden (pytefas) alınır; "
        "erişilemediğinde son bilinen yedek fiyatlar kullanılır (tabloda \"Yedek\" olarak işaretlenir).",
        alt_baslik_stili,
    ))

    doc.build(story)


pdf_raporu_uret("public/portfoy_raporu.pdf")

# ------------------------------------------------------------------------------
# UYARI WEBHOOK'U (opsiyonel, eşik aşılırsa)
# ------------------------------------------------------------------------------
def uyari_gonder(url: str, mesaj: str):
    if not url:
        return
    try:
        payload = json.dumps({"text": mesaj}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        ctx = ssl.create_default_context()
        urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx)
    except Exception as e:
        print(f"Bildirim gönderilemedi: {e}")


if abs(dogru_genel_degisim) >= BILDIRIM_ESIK:
    uyari_gonder(
        WEBHOOK_URL,
        f"BES Portföy uyarısı: toplam değişim %{dogru_genel_degisim:.2f} "
        f"(eşik: %{BILDIRIM_ESIK}). Tarih: {tarih_str}",
    )

# ------------------------------------------------------------------------------
# HTML ÜRETİMİ
# ------------------------------------------------------------------------------
html_icerik = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <title>BES Canli Takip Paneli</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'unsafe-inline'; img-src 'self' data:;">
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background-color:#f8fafc; margin:0; padding:20px; color:#333;">
    <div style="max-width:1100px; margin:0 auto; background:white; padding:30px; border-radius:16px; box-shadow:0 10px 25px rgba(0,0,0,0.03); border:1px solid #e2e8f0;">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:2px solid #f1f5f9; padding-bottom:20px; margin-bottom:25px; flex-wrap:wrap; gap:15px;">
            <div>
                <h1 style="margin:0; color:#0f172a; font-size:24px; font-weight:800; letter-spacing:-0.5px;">Garanti BES Portföy Takip Paneli</h1>
                <p style="color:#64748b; font-size:14px; margin:5px 0 0 0;">Son Güncelleme: <strong>{tarih_str} - {bugun.strftime('%H:%M')}</strong> ·
                <a href="portfoy_raporu.pdf" style="color:#2563eb; text-decoration:none; font-weight:600;">⬇ PDF indir</a> ·
                <a href="portfoy_raporu.csv" style="color:#64748b; text-decoration:none; font-weight:500; font-size:12px;">CSV</a></p>
            </div>
        </div>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:20px; margin-bottom:30px;">
            <div style="background:#f8fafc; padding:20px; border-radius:12px; border:1px solid #e2e8f0;">
                <div style="font-size:13px; font-weight:600; color:#64748b; text-transform:uppercase;">Yatırılan Toplam Anapara</div>
                <div style="font-size:26px; font-weight:800; color:#0f172a; margin-top:8px;">{toplam_maliyet:.2f} TL</div>
                <div style="font-size:12px; color:#64748b; margin-top:5px;">Dönem: {ay_sayisi}. Ay</div>
            </div>
            <div style="background:#f0fdf4; padding:20px; border-radius:12px; border:1px solid #bbf7d0; border-left:6px solid #10b981;">
                <div style="font-size:13px; font-weight:600; color:#15803d; text-transform:uppercase;">Toplam Net Portföy Kârı</div>
                <div style="font-size:26px; font-weight:800; color:#166534; margin-top:8px;">+{genel_kar:.2f} TL</div>
                {gunluk_kar_html}
            </div>
            <div style="background:#f0fdfa; padding:20px; border-radius:12px; border:1px solid #99f6e4;">
                <div style="font-size:13px; font-weight:600; color:#0f766e; text-transform:uppercase;">Toplam Portföy Büyümesi</div>
                <div style="font-size:26px; font-weight:800; color:#115e59; margin-top:8px;">+{dogru_genel_degisim:.2f}%</div>
            </div>
            <div style="background:#fefce8; padding:20px; border-radius:12px; border:1px solid #fef08a;">
                <div style="font-size:13px; font-weight:600; color:#854d0e; text-transform:uppercase;">Enflasyona Göre (varsayım)</div>
                <div style="font-size:22px; font-weight:800; color:{enf_renk}; margin-top:8px;">%{enflasyon_farki:+.2f} {enf_yon}</div>
                <div style="font-size:11px; color:#a16207; margin-top:5px;">{enflasyon_kaynagi}</div>
            </div>
        </div>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:20px; margin-bottom:30px;">
            <div style="background:#f8fafc; padding:16px; border-radius:12px; border:1px solid #e2e8f0;">
                <div style="font-size:12px; font-weight:600; color:#64748b; text-transform:uppercase;">Volatilite</div>
                <div style="font-size:16px; font-weight:700; color:#0f172a; margin-top:6px;">{volatilite_html}</div>
            </div>
            <div style="background:#f8fafc; padding:16px; border-radius:12px; border:1px solid #e2e8f0;">
                <div style="font-size:12px; font-weight:600; color:#64748b; text-transform:uppercase;">Maks. Düşüş (Drawdown)</div>
                <div style="font-size:16px; font-weight:700; color:#0f172a; margin-top:6px;">{drawdown_html}</div>
            </div>
        </div>

        <div style="border:1px solid #e2e8f0; border-radius:12px; padding:20px; margin-bottom:30px;">
            <h3 style="margin-top:0; margin-bottom:15px; color:#1e293b; font-size:15px;">📅 Dönemsel Getiriler <span style="font-weight:400; color:#94a3b8; font-size:11px;">· panelin kendi geçmiş verisinden</span></h3>
            <div style="display:flex; gap:12px; flex-wrap:wrap;">
                {donem_kartlari_html}
            </div>
        </div>

        <div style="border:1px solid #e2e8f0; border-radius:12px; padding:20px; margin-bottom:30px; display:flex; gap:24px; flex-wrap:wrap; align-items:center;">
            <div>
                <h3 style="margin-top:0; margin-bottom:12px; color:#1e293b; font-size:15px;">🥧 Fon Dağılımı</h3>
                {donut_svg}
            </div>
            <div style="flex:1; min-width:160px;">
                <div style="font-size:11px; font-weight:600; color:#94a3b8; text-transform:uppercase; margin-bottom:10px;">{len(fon_kayitlari)} Fon · Ağırlık(%)</div>
                {lejant_html}
            </div>
        </div>

        <div style="border:1px solid #e2e8f0; border-radius:12px; padding:20px; margin-bottom:30px; background:#fcfcfd;">
            <h3 style="margin-top:0; margin-bottom:15px; color:#1e293b; font-size:15px;">📈 Tarihsel Portföy Değeri</h3>
            {tarihsel_grafik_svg}
        </div>


        <div style="overflow-x:auto; margin-bottom:30px; border:1px solid #e2e8f0; border-radius:12px;">
            <table style="width:100%; border-collapse:collapse; text-align:left; font-size:14px;">
                <thead>
                    <tr style="background:#1e293b; color:white; font-weight:600;">
                        <th style="padding:14px;">Fon Kodu</th>
                        <th style="padding:14px;">Fon Adı</th>
                        <th style="padding:14px;">Ağırlık</th>
                        <th style="padding:14px;">Maliyet Payı</th>
                        <th style="padding:14px;">Giriş Fiyatı (05.08)</th>
                        <th style="padding:14px;">Güncel Fiyat</th>
                        <th style="padding:14px;">Toplam Değişim</th>
                        <th style="padding:14px; text-align:center;">Günlük Değişim</th>
                        <th style="padding:14px;">Net Kâr/Zarar</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rapor_data)}
                </tbody>
            </table>
        </div>

        <div style="border:1px solid #e2e8f0; border-radius:12px; padding:25px; background:#f8fafc; margin-bottom:30px;">
            <h3 style="margin-top:0; margin-bottom:25px; color:#1e293b; font-size:16px;">📊 Fon Bazlı Net Kâr Dağılım Grafiği (TL)</h3>
            <div style="display:flex; justify-content:space-around; align-items:flex-end; max-width:700px; margin:0 auto; height:240px; border-bottom:2px solid #cbd5e1; padding-bottom:5px; gap:10px;">
                {"".join(grafik_cubuklari_html)}
            </div>
        </div>

        <div style="border:1px solid #e2e8f0; border-radius:12px; padding:20px;">
            <h3 style="margin-top:0; margin-bottom:12px; color:#1e293b; font-size:15px;">🗓 Katkı Payı Takvimi</h3>
            <div>{katki_html}</div>
        </div>
    </div>
</body>
</html>
"""

os.makedirs("public", exist_ok=True)
with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(html_icerik)

print("Panel güncellendi. Kaynak:", "canlı API" if piyasa_havuzu else "yedek fiyatlar")
