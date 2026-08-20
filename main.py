import os
import ssl
import json
import html
import urllib.request
import urllib.parse
import statistics
from datetime import datetime

# ==============================================================================
# HATA ÖNLEYİCİ: PUBLIC KLASÖRÜNÜ EN BAŞTA KESİN OLARAK OLUŞTURMA
# ==============================================================================
os.makedirs("public", exist_ok=True)

# ==============================================================================
# AYARLAR
# ==============================================================================
aylik_odeme = 5000.0
baslangic_tarihi = datetime(2026, 8, 5)
bugun = datetime.now()

AYLIK_ENFLASYON_VARSAYIMI = 3.0  
BILDIRIM_ESIK = 5.0

WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
TCMB_API_KEY = os.environ.get("TCMB_API_KEY", "").strip()
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
    'GEL': 0.443463, 'GEH': 2.914848, 'EMY': 0.010793, 'GHG': 1.221447, 'GHH': 0.405183,
}

tarih_str = bugun.strftime('%d-%m-%Y')
tarih_iso = bugun.strftime('%Y-%m-%d')

piyasa_havuzu = {}
try:
    # URL üzerindeki boşluk hatası tamamen düzeltildi
    url = "https://devtunnels.ms"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=8) as response:
        canli_json = json.loads(response.read().decode())
    for item in canli_json:
        if item.get('kod') in fon_tanimlari:
            piyasa_havuzu[item['kod']] = float(item['fiyat'])
except Exception as e:
    print(f"Canli borsa hatti yedek fiyata gecti: {e}")

def gecmisi_yukle(path: str) -> list:
    if not os.path.exists(path): return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except: return []

def gecmisi_kaydet(path: str, gecmis: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(gecmis, f, ensure_ascii=False, indent=2)

gecmis = gecmisi_yukle(HISTORY_PATH)

# ==============================================================================
# HESAPLAMA MOTORU
# ==============================================================================
rapor_data = []
grafik_cubuklari_html = []
fon_kayitlari = []  
renkler = ['#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6']

toplam_maliyet = 0.0
toplam_guncel_deger = 0.0

for idx, (kod, info) in enumerate(fon_tanimlari.items()):
    giris_fiy = float(info['giris_fiyati'])
    guncel_fiy = float(piyasa_havuzu.get(kod, YEDEK_FIYATLAR.get(kod, giris_fiy)))

    toplam_degisim_orani = ((guncel_fiy - giris_fiy) / giris_fiy) * 100
    fon_maliyeti = toplam_anapara * info['agirlik']
    fon_guncel_degeri = fon_maliyeti * (1 + (toplam_degisim_orani / 100))
    fon_net_kar_zarar = fon_guncel_degeri - fon_maliyeti

    toplam_maliyet += fon_maliyeti
    toplam_guncel_deger += fon_guncel_degeri

    fon_kayitlari.append({
        "kod": kod, "ad": info['ad'], "agirlik": info['agirlik'] * 100,
        "maliyet": fon_maliyeti, "giris": giris_fiy, "guncel": guncel_fiy,
        "degisim": toplam_degisim_orani, "kar": fon_net_kar_zarar
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
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#0f172a; font-family:monospace; font-weight:500;'>{guncel_fiy:.6f} TL <span style="color:#059669;font-size:11px;font-weight:600;">● Canli</span></td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:{renk}; font-weight:600;'>{arti_eksi}{toplam_degisim_orani:.2f}%</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; font-weight:bold; color:{renk};'>{arti_eksi}{fon_net_kar_zarar:.2f} TL</td>
    </tr>
    """)

    bar_height = max(5, min(int(abs(fon_net_kar_zarar) * 1.5), 180))
    grafik_cubuklari_html.append(f"""
    <div style="display:flex; flex-direction:column; align-items:center; flex:1; min-width:60px;">
        <div style="font-size:11px; font-weight:bold; margin-bottom:5px; color:#1e293b;">{arti_eksi}{fon_net_kar_zarar:.2f} TL</div>
        <div style="width:100%; background-color:{renkler[idx % len(renkler)]}; height:{bar_height}px; border-radius:6px 6px 0 0;"></div>
        <div style="margin-top:8px; font-weight:bold; font-size:13px; color:#475569;">{kod}</div>
    </div>
    """)

genel_kar = toplam_guncel_deger - toplam_maliyet
dogru_genel_degisim = (genel_kar / toplam_maliyet) * 100 if toplam_maliyet else 0.0

bugun_kaydi = {"tarih": tarih_iso, "toplam_deger": round(toplam_guncel_deger, 2), "toplam_kar": round(genel_kar, 2), "toplam_degisim": round(dogru_genel_degisim, 4)}
gecmis = [g for g in gecmis if g.get("tarih") != tarih_iso]
gecmis.append(bugun_kaydi)
gecmis.sort(key=lambda g: g["tarih"])
gecmisi_kaydet(HISTORY_PATH, gecmis)

volatilite_html = "Yetersiz veri"
drawdown_html = "Yetersiz veri"
if len(gecmis) >= 2:
    degerler = [g["toplam_deger"] for g in gecmis]
    gunluk_getiriler = [(degerler[i] - degerler[i - 1]) / degerler[i - 1] * 100 for i in range(1, len(degerler)) if degerler[i - 1] != 0]
    if len(gunluk_getiriler) >= 2: volatilite_html = f"%{statistics.stdev(gunluk_getiriler):.2f}"
    zirve = degerler
    maks_dusus = 0.0
    for v in degerler:
        zirve = max(zirve, v)
        dusus = (v - zirve) / zirve * 100 if zirve else 0
        maks_dusus = min(maks_dusus, dusus)
    drawdown_html = f"%{maks_dusus:.2f}"

tahmini_enflasyon = AYLIK_ENFLASYON_VARSAYIMI * ay_sayisi
enflasyon_kaynagi = "Manuel Varsayim"
enflasyon_farki = dogru_genel_degisim - tahmini_enflasyon
enf_yon = "Uzerinde" if enflasyon_farki >= 0 else "Altinda"
enf_renk = "#059669" if enflasyon_farki >= 0 else "#dc2626"

# ==============================================================================
# REPORTLAB PDF GENERATOR
# ==============================================================================
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors

def pdf_raporu_uret(yol: str):
    doc = SimpleDocTemplate(yol, pagesize=A4, leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('T1', fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=colors.HexColor('#0f172a'))
    meta_style = ParagraphStyle('M1', fontName='Helvetica', fontSize=10, leading=14, textColor=colors.HexColor('#64748b'), spaceAfter=15)
    sec_style = ParagraphStyle('S1', fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=colors.HexColor('#1e293b'), spaceBefore=12, spaceAfter=6)
    c_style = ParagraphStyle('C1', fontName='Helvetica', fontSize=9, leading=12, textColor=colors.HexColor('#334155'))
    c_style_b = ParagraphStyle('C2', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=colors.HexColor('#0f172a'))
    c_style_white = ParagraphStyle('C3', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=colors.white)

    story.append(Paragraph("Garanti BES Portfoy Takip Raporu", title_style))
    story.append(Paragraph(f"Tarih: {tarih_str} &nbsp;|&nbsp; Donem: {ay_sayisi}. Ay", meta_style))

    # Özet Kart Tablosu
    ozet_veri = [
        [Paragraph("Yatirilan Anapara", c_style), Paragraph("Net Kar", c_style), Paragraph("Portfoy Buyumesi", c_style), Paragraph("Enflasyona Gore", c_style)],
        [Paragraph(f"{toplam_maliyet:.2f} TL", c_style_b), Paragraph(f"+{genel_kar:.2f} TL", c_style_b), Paragraph(f"+%{dogru_genel_degisim:.2f}", c_style_b), Paragraph(f"%{enflasyon_farki:+.2f} {enf_yon}", c_style_b)]
    ]
    t_ozet = Table(ozet_veri, colWidths=[47*mm]*4)
    t_ozet.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#f1f5f9")),
        ("BACKGROUND",(0,1),(-1,1),colors.HexColor("#f8fafc")),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e2e8f0")),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6)
    ]))
    story.append(t_ozet)

    # Detaylar Tablosu
    story.append(Paragraph("Fon Bazli Detaylar", sec_style))
