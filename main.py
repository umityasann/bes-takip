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
# PDF İçerisine Grafik Çizmek İçin Gerekli Olan ReportLab Modülleri
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.barcharts import VerticalBarChart

# ==============================================================================
# AYARLAR
# ==============================================================================
aylik_odeme = 5000.0
baslangic_tarihi = datetime(2026, 8, 5)
bugun = datetime.now()

AYLIK_ENFLASYON_VARSAYIMI = 3.0  # % — sadece TCMB erişilemezse kullanılır
BILDIRIM_ESIK = 5.0

WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
TCMB_API_KEY = os.environ.get("TCMB_API_KEY", "").strip()

MAX_RESPONSE_BYTES = 200_000  
REQUEST_TIMEOUT = 5

HISTORY_PATH = "data/history.json"  

ay_sayisi = (bugun.year - baslangic_tarihi.year) * 12 + (bugun.month - baslangic_tarihi.month) + 1
if bugun.day < baslangic_tarihi.day and ay_sayisi > 1:
    ay_sayisi -= 1

toplam_anapara = float(aylik_odeme * ay_sayisi)

fon_tanimlari = {
    'GEL': {'ad': 'Para Piyasasi Emeklilik Yatirim Fonu', 'agirlik': 0.20, 'giris_fiyati': 0.436406},
    'GEH': {'ad': 'Hisse Senedi Emeklilik Yatirim Fonu', 'agirlik': 0.30, 'giris_fiyati': 2.779911},
    'EMY': {'ad': 'Altin Emeklilik Yatirim Fonu', 'agirlik': 0.20, 'giris_fiyati': 0.009987},
    'GHG': {'ad': 'Dis Borclanma Araclari Emeklilik Yatirim Fonu', 'agirlik': 0.20, 'giris_fiyati': 1.201487},
    'GHH': {'ad': 'Surdurulebilirlik Hisse Senedi Emeklilik Yatirim Fonu', 'agirlik': 0.10, 'giris_fiyati': 0.395887},
}

YEDEK_FIYATLAR = {
    'GEL': 0.442970, 'GEH': 2.833800, 'EMY': 0.010863, 'GHG': 1.215962, 'GHH': 0.400294,
}

tarih_str = bugun.strftime('%d-%m-%Y')
tarih_iso = bugun.strftime('%Y-%m-%d')

FON_KODLARI = list(fon_tanimlari.keys())

def tefas_fiyatlarini_cek(fon_kodlari: list, gun_sayisi_geriye: int = 7) -> dict:
    crawler = Crawler(timeout=REQUEST_TIMEOUT * 4, max_retry=3)
    for gun_ofset in range(gun_sayisi_geriye):
        tarih = (bugun - timedelta(days=gun_ofset)).strftime("%Y-%m-%d")
        try:
            df = crawler.fetch(tarih, columns="info", kind="EMK")
        except (TefasAPIError, TefasRateLimitError) as e:
            print(f"TEFAS API hatasi ({tarih}): {e}")
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
            print(f"TEFAS verisi bulundu: {tarih} ({len(havuz)}/{len(fon_kodlari)} fon)")
            return havuz
    return {}

try:
    piyasa_havuzu = tefas_fiyatlarini_cek(FON_KODLARI)
except Exception as e:
    print(f"TEFAS entegrasyonu basarisiz: {e}")
    piyasa_havuzu = {}

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

# ==============================================================================
# FON HESAPLAMALARI
# ==============================================================================
rapor_data = []
grafik_cubuklari_html = []
fon_kayitlari = []  
renkler = ['#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6']

toplam_maliyet = 0.0
toplam_guncel_deger = 0.0

for idx, (kod, info) in enumerate(fon_tanimlari.items()):
    giris_fiy = float(info['giris_fiyati'])

    if kod in piyasa_havuzu and piyasa_havuzu[kod] > 0:
        guncel_fiy = piyasa_havuzu[kod]
        kaynak_etiket = '<span style="color:#059669;font-size:11px;font-weight:600;">● Canli</span>'
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
        "kaynak": "Canli" if kod in piyasa_havuzu and piyasa_havuzu[kod] > 0 else "Yedek",
    })

    renk = "green" if fon_net_kar_zarar >= 0 else "red"
    arti_eksi = "+" if fon_net_kar_zarar >= 0 else ""
    ad_guvenli = html.escape(info['ad'])

    rapor_data.append(f"""
    <tr>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; font-weight:bold; color:#1e293b;'>{kod}</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#475569;'>{ad_guvenli}</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#475569; font-weight:500;'>{info['agirlik']*100:.1f}%</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#475569;'>{fon_maliyeti:.2f} TL</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#64748b; font-family:monospace;'>{giris_fiy:.6f} TL</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#0f172a; font-family:monospace; font-weight:500;'>{guncel_fiy:.6f} TL {kaynak_etiket}</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:{renk}; font-weight:600;'>{arti_eksi}{toplam_degisim_orani:.2f}%</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; font-weight:bold; color:{renk};'>{arti_eksi}{fon_net_kar_zarar:.2f} TL</td>
    </tr>
    """)

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

bugun_kaydi = {
    "tarih": tarih_iso,
    "toplam_deger": round(toplam_guncel_deger, 2),
    "toplam_kar": round(genel_kar, 2),
    "toplam_degisim": round(dogru_genel_degisim, 4),
}
gecmis = [g for g in gecmis if g.get("tarih") != tarih_iso]
gecmis.append(bugun_kaydi)
gecmis.sort(key=lambda g: g["tarih"])
gecmisi_kaydet(HISTORY_PATH, gecmis)

volatilite_html = "Yetersiz veri"
drawdown_html = "Yetersiz veri"
if len(gecmis) >= 2:
    degerler = [g["toplam_deger"] for g in gecmis]
    gunluk_getiriler = [(degerler[i] - degerler[i - 1]) / degerler[i - 1] * 100 for i in range(1, len(degerler)) if degerler[i - 1] != 0]
    if len(gunluk_getiriler) >= 2:
        volatilite_html = f"%{statistics.stdev(gunluk_getiriler):.2f}"
    zirve = degerler[0]
    maks_dusus = 0.0
    for v in degerler:
        zirve = max(zirve, v)
        dusus = (v - zirve) / zirve * 100 if zirve else 0
        maks_dusus = min(maks_dusus, dusus)
    drawdown_html = f"%{maks_dusus:.2f}"

def tufe_kumulatif_getir(api_key: str, baslangic: datetime, bitis: datetime):
    if not api_key: return None
    try:
        params = urllib.parse.urlencode({"series": "TP.FG.J0", "startDate": baslangic.strftime("%d-%m-%Y"), "endDate": bitis.strftime("%d-%m-%Y"), "frequency": "5", "type": "json"})
        req = urllib.request.Request(f"https://tcmb.gov.tr{params}", headers={"key": api_key})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        degerler = [float(item["TP_FG_J0"]) for item in data.get("items", []) if item.get("TP_FG_J0") is not None]
        return (degerler[-1] - degerler[0]) / degerler[0] * 100 if len(degerler) >= 2 else None
    except: return None

tahmini_enflasyon = tufe_kumulatif_getir(TCMB_API_KEY, baslangic_tarihi, bugun)
if tahmini_enflasyon is not None:
    enflasyon_kaynagi = "TCMB EVDS (Gerçek)"
else:
    tahmini_enflasyon = AYLIK_ENFLASYON_VARSAYIMI * ay_sayisi
    enflasyon_kaynagi = "Manuel Varsayım"

enflasyon_farki = dogru_genel_degisim - tahmini_enflasyon
enf_yon = "Uzerinde" if enflasyon_farki >= 0 else "Altinda"
enf_renk = "#059669" if enflasyon_farki >= 0 else "#dc2626"

def svg_cizgi_grafik(gecmis: list, genislik=640, yukseklik=140) -> str:
