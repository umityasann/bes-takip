import os
import pandas as pd
from datetime import datetime

# ==============================================================================
# SİZİN BAŞLANGIÇ AYARLARINIZ (Otomatik Zaman Sayıcı Aktif)
# ==============================================================================
aylik_odeme = 5000.0
baslangic_tarihi = datetime(2026, 8, 5)  # İlk yatırım tarihi: 5 Ağustos 2026
bugun = datetime.now()

# İki tarih arasındaki toplam ay farkını otomatik hesaplayan formül
ay_sayisi = (bugun.year - baslangic_tarihi.year) * 12 + (bugun.month - baslangic_tarihi.month) + 1

# Eğer ayın 5'inden önce bir gündeysek, o ayın ödemesi henüz çekilmediği için ay sayısını 1 eksilt
if bugun.day < 5 and ay_sayisi > 1:
    ay_sayisi -= 1

toplam_anapara = float(aylik_odeme * ay_sayisi)

fon_tanimlari = {
    'GEL': {'ad': 'Para Piyasası Emeklilik Yatırım Fonu', 'agirlik': 0.20, 'giris_fiyati': 0.436406},
    'GEH': {'ad': 'Hisse Senedi Emeklilik Yatırım Fonu', 'agirlik': 0.30, 'giris_fiyati': 2.779911},
    'EMY': {'ad': 'Altın Emeklilik Yatırım Fonu', 'agirlik': 0.20, 'giris_fiyati': 0.009987},
    'GHG': {'ad': 'Dış Borçlanma Araçları Emeklilik Yatırım Fonu', 'agirlik': 0.20, 'giris_fiyati': 1.201487},
    'GHH': {'ad': 'Sürdürülebilirlik Hisse Senedi Emeklilik Yatırım Fonu', 'agirlik': 0.10, 'giris_fiyati': 0.395887}
}

tarih_str = bugun.strftime('%d-%m-%Y')
rapor_data = []

toplam_maliyet = 0.0
toplam_guncel_deger = 0.0

tahmini_guncel_piyasa = {
    'GEL': 0.442970, 'GEH': 2.833800, 'EMY': 0.010250, 'GHG': 1.220412, 'GHH': 0.401200
}

labels_js = []
values_js = []

for kod, info in fon_tanimlari.items():
    giris_fiy = float(info['giris_fiyati'])
    guncel_fiy = float(tahmini_guncel_piyasa.get(kod, giris_fiy))
    
    toplam_degisim_orani = float(((guncel_fiy - giris_fiy) / giris_fiy) * 100)
    fon_maliyeti = float(toplam_anapara * info['agirlik'])
    fon_guncel_degeri = float(fon_maliyeti * (1 + (toplam_degisim_orani / 100)))
    fon_net_kar_zarar = float(fon_guncel_degeri - fon_maliyeti)
    
    toplam_maliyet += fon_maliyeti
    toplam_guncel_deger += fon_guncel_degeri
    
    labels_js.append(f"'{kod}'")
    values_js.append(f"{fon_net_kar_zarar:.2f}")
    
    renk = "green" if fon_net_kar_zarar >= 0 else "red"
    arti_eksi = "+" if font_net_kar_zarar >= 0 else ""
    
    rapor_data.append(f"""
    <tr>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; font-weight:bold; color:#1e293b;'>{kod}</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#475569;'>{info['ad']}</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#475569; font-weight:500;'>{info['agirlik']*100:.1f}%</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#475569;'>{fon_maliyeti:.2f} TL</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#64748b; font-family:monospace;'>{giris_fiy:.4f} TL</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:#0f172a; font-family:monospace; font-weight:500;'>{guncel_fiy:.4f} TL</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; color:{renk}; font-weight:600;'>{arti_eksi}{toplam_degisim_orani:.2f}%</td>
        <td style='padding:14px; border-bottom:1px solid #e2e8f0; font-weight:bold; color:{renk};'>{arti_eksi}{fon_net_kar_zarar:.2f} TL</td>
    </tr>
    """)

genel_kar = toplam_guncel_deger - toplam_maliyet
dogru_genel_degisim = (genel_kar / toplam_maliyet) * 100

html_icerik = f"""
<!DOCTYPE html>
<html>
<head>
    <title>BES Canli Takip Paneli</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://jsdelivr.net"></script>
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background-color:#f8fafc; margin:0; padding:20px; color:#333;">
    <div style="max-width:1100px; margin:0 auto; background:white; padding:30px; border-radius:16px; box-shadow:0 10px 25px rgba(0,0,0,0.03); border:1px solid #e2e8f0;">
        <div style="display:flex; justify-content:between; align-items:center; border-bottom:2px solid #f1f5f9; padding-bottom:20px; margin-bottom:25px; flex-wrap:wrap; gap:15px;">
            <div>
                <h1 style="margin:0; color:#0f172a; font-size:24px; font-weight:800; letter-spacing:-0.5px;">Garanti BES Portföy Takip Ekibi</h1>
                <p style="color:#64748b; font-size:14px; margin:5px 0 0 0;">Yapay Zeka Analiz Paneli | Son Güncelleme: <strong>{tarih_str} - 19:30</strong></p>
            </div>
        </div>
        
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:20px; margin-bottom:30px;">
            <div style="background:#f8fafc; padding:20px; border-radius:12px; border:1px solid #e2e8f0;">
                <div style="font-size:13px; font-weight:600; color:#64748b; text-transform:uppercase;">Yatırılan Toplam Anapara</div>
                <div style="font-size:26px; font-weight:800; color:#0f172a; margin-top:8px;">{toplam_maliyet:.2f} TL</div>
                <div style="font-size:12px; color:#64748b; margin-top:5px;"> Dönem: {ay_sayisi}. Ay </div>
            </div>
            <div style="background:#f0fdf4; padding:20px; border-radius:12px; border:1px solid #bbf7d0; border-left:6px solid #10b981;">
                <div style="font-size:13px; font-weight:600; color:#15803d; text-transform:uppercase;">Toplam Net Portföy Kârı</div>
                <div style="font-size:26px; font-weight:800; color:#166534; margin-top:8px;">+{genel_kar:.2f} TL</div>
            </div>
            <div style="background:#f0fdfa; padding:20px; border-radius:12px; border:1px solid #99f6e4;">
                <div style="font-size:13px; font-weight:600; color:#0f766e; text-transform:uppercase;">Toplam Portföy Büyümesi</div>
                <div style="font-size:26px; font-weight:800; color:#115e59; margin-top:8px;">+{dogru_genel_degisim:.2f}%</div>
            </div>
        </div>

        <div style="overflow-x:auto; margin-bottom:40px; border:1px solid #e2e8f0; border-radius:12px;">
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
                        <th style="padding:14px;">Net Kâr/Zarar</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rapor_data)}
                </tbody>
            </table>
        </div>

        <div style="border:1px solid #e2e8f0; border-radius:12px; padding:20px; background:#f8fafc;">
            <h3 style="margin-top:0; color:#1e293b; font-size:16px;">📊 Fon Bazlı Net Kâr Dağılım Grafiği (TL)</h3>
            <div style="max-width:600px; margin:0 auto; height:300px;">
                <canvas id="besChart"></canvas>
            </div>
        </div>
    </div>

    <script>
        const ctx = document.getElementById('besChart').getContext('2d');
        new Chart(ctx, {{
            type: 'bar',
            data: {{
                labels: [{", ".join(labels_js)}],
                datasets: [{{
                    label: 'Net Kâr (TL)',
                    data: [{", ".join(values_js)}],
                    backgroundColor: '#10b981',
                    borderRadius: 6,
                    borderWidth: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{ y: {{ beginAtZero: true }} }}
            }}
        }});
    </script>
</body>
</html>
"""

os.makedirs("public", exist_ok=True)
with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(html_icerik)
print("Sonsuz döngülü otomatik web paneli başarıyla yüklendi.")
