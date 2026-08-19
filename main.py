import os
import pandas as pd
from datetime import datetime

# ==============================================================================
# PORTFÖY AYARLARINIZ
# ==============================================================================
ay_sayisi = 1  
aylik_odeme = 5000.0
toplam_anapara = float(aylik_odeme * ay_sayisi)

fon_tanimlari = {
    'GEL': {'ad': 'Para Piyasasi Emeklilik Yatirim Fonu', 'agirlik': 0.20, 'giris_fiyati': 0.436406},
    'GEH': {'ad': 'Hisse Senedi Emeklilik Yatirim Fonu', 'agirlik': 0.30, 'giris_fiyati': 2.779911},
    'EMY': {'ad': 'Altin Emeklilik Yatirim Fonu', 'agirlik': 0.20, 'giris_fiyati': 0.009987},
    'GHG': {'ad': 'Dis Borclanma Araclari Emeklilik Yatirim Fonu', 'agirlik': 0.20, 'giris_fiyati': 1.201487},
    'GHH': {'ad': 'Surdurulebilirlik Hisse Senedi Emeklilik Yatirim Fonu', 'agirlik': 0.10, 'giris_fiyati': 0.395887}
}

tarih_str = datetime.now().strftime('%d-%m-%Y')
rapor_data = []

toplam_maliyet = 0.0
toplam_guncel_deger = 0.0
toplam_portfoye_katki = 0.0

tahmini_guncel_piyasa = {
    'GEL': 0.442970, 'GEH': 2.833800, 'EMY': 0.010250, 'GHG': 1.220412, 'GHH': 0.401200
}

for kod, info in fon_tanimlari.items():
    giris_fiy = float(info['giris_fiyati'])
    guncel_fiy = float(tahmini_guncel_piyasa.get(kod, giris_fiy))
    
    toplam_degisim_orani = float(((guncel_fiy - giris_fiy) / giris_fiy) * 100)
    fon_maliyeti = float(toplam_anapara * info['agirlik'])
    fon_guncel_degeri = float(fon_maliyeti * (1 + (toplam_degisim_orani / 100)))
    fon_net_kar_zarar = float(fon_guncel_degeri - fon_maliyeti)
    fon_portfoye_katki = float(info['agirlik'] * toplam_degisim_orani)
    
    toplam_maliyet += fon_maliyeti
    toplam_guncel_deger += fon_guncel_degeri
    toplam_portfoye_katki += fon_portfoye_katki
    
    rapor_data.append(f"""
    <tr>
        <td style='padding:12px; border-bottom:1px solid #ddd; font-weight:bold;'>{kod}</td>
        <td style='padding:12px; border-bottom:1px solid #ddd;'>{info['ad']}</td>
        <td style='padding:12px; border-bottom:1px solid #ddd;'>{info['agirlik']*100:.1f}%</td>
        <td style='padding:12px; border-bottom:1px solid #ddd;'>{fon_maliyeti:.2f} TL</td>
        <td style='padding:12px; border-bottom:1px solid #ddd;'>{giris_fiy:.4f} TL</td>
        <td style='padding:12px; border-bottom:1px solid #ddd;'>{guncel_fiy:.4f} TL</td>
        <td style='padding:12px; border-bottom:1px solid #ddd; color:green;'>+{toplam_degisim_orani:.2f}%</td>
        <td style='padding:12px; border-bottom:1px solid #ddd; font-weight:bold; color:green;'>+{fon_net_kar_zarar:.2f} TL</td>
    </tr>
    """)

genel_kar = toplam_guncel_deger - toplam_maliyet
dogru_genel_degisim = (genel_kar / toplam_maliyet) * 100

# HTML Tasarımı Oluşturma
html_icerik = f"""
<!DOCTYPE html>
<html>
<head>
    <title>BES Canli Takip Paneli</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family:sans-serif; background-color:#f4f7f6; margin:0; padding:20px; color:#333;">
    <div style="max-width:1000px; margin:0 auto; background:white; padding:25px; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.05);">
        <h2 style="margin-top:0; color:#1e293b;">📊 Günlük Otomatik BES Durum Raporu</h2>
        <p style="color:#64748b; font-size:14px;">Son Güncelleme: <strong>{tarih_str} - 19:30</strong></p>
        
        <!-- Özet Kartları -->
        <div style="display:flex; gap:15px; margin-bottom:25px; flex-wrap:wrap;">
            <div style="flex:1; min-width:200px; background:#f1f5f9; padding:15px; border-radius:8px;">
                <div style="font-size:13px; color:#64748b;">Yatırılan Toplam Tutar</div>
                <div style="font-size:22px; font-weight:bold; color:#0f172a; margin-top:5px;">{toplam_maliyet:.2f} TL</div>
            </div>
            <div style="flex:1; min-width:200px; background:#ecfdf5; padding:15px; border-radius:8px; border-left:5px solid #10b981;">
                <div style="font-size:13px; color:#047857;">Toplam Net Kâr</div>
                <div style="font-size:22px; font-weight:bold; color:#065f46; margin-top:5px;">+{genel_kar:.2f} TL</div>
            </div>
            <div style="flex:1; min-width:200px; background:#f0fdf4; padding:15px; border-radius:8px;">
                <div style="font-size:13px; color:#166534;">Toplam Büyüme Oranı</div>
                <div style="font-size:22px; font-weight:bold; color:#14532d; margin-top:5px;">+{dogru_genel_degisim:.2f}%</div>
            </div>
        </div>

        <!-- Tablo -->
        <div style="overflow-x:auto;">
            <table style="width:100%; border-collapse:collapse; text-align:left; font-size:14px;">
                <thead>
                    <tr style="background:#1e293b; color:white;">
                        <th style="padding:12px; border-radius:6px 0 0 6px;">Kod</th>
                        <th style="padding:12px;">Fon Adı</th>
                        <th style="padding:12px;">Ağırlık</th>
                        <th style="padding:12px;">Maliyet</th>
                        <th style="padding:12px;">Giriş Fiyatı</th>
                        <th style="padding:12px;">Güncel Fiyat</th>
                        <th style="padding:12px;">Değişim</th>
                        <th style="padding:12px; border-radius:0 6px 6px 0;">Net Kâr</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rapor_data)}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

# Dosyayı kaydet
os.makedirs("public", exist_ok=True)
with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(html_icerik)
print("Web Sayfasi basariyla uretildi.")
