import os
import pandas as pd
from datetime import datetime
import openpyxl
from openpyxl.chart import BarChart, PieChart, Reference

# ==============================================================================
# SİZİN PORTFÖY AYARLARINIZ
# ==============================================================================
ay_sayisi = 1  
aylik_odeme = 5000.0
toplam_anapara = float(aylik_odeme * ay_sayisi)

fon_tanimlari = {
    'GEL': {'ad': 'Para Piyasası Emeklilik Yatırım Fonu', 'agirlik': 0.20, 'giris_fiyati': 0.436406},
    'GEH': {'ad': 'Hisse Senedi Emeklilik Yatırım Fonu', 'agirlik': 0.30, 'giris_fiyati': 2.779911},
    'EMY': {'ad': 'Altın Emeklilik Yatırım Fonu', 'agirlik': 0.20, 'giris_fiyati': 0.009987},
    'GHG': {'ad': 'Dış Borçlanma Araçları Emeklilik Yatırım Fonu', 'agirlik': 0.20, 'giris_fiyati': 1.201487},
    'GHH': {'ad': 'Sürdürülebilirlik Hisse Senedi Emeklilik Yatırım Fonu', 'agirlik': 0.10, 'giris_fiyati': 0.395887}
}

tarih_str = datetime.now().strftime('%Y-%m-%d')
rapor_data = []

toplam_maliyet = 0.0
toplam_guncel_deger = 0.0
toplam_portfoye_katki = 0.0

tahmini_guncel_piyasa = {
    'GEL': 0.442970, 
    'GEH': 2.833800,
    'EMY': 0.010250,
    'GHG': 1.220412,
    'GHH': 0.401200
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
    
    rapor_data.append([
        kod, 
        info['ad'], 
        float(info['agirlik'] * 100),
        round(fon_maliyeti, 2),
        round(giris_fiy, 3),          
        round(guncel_fiy, 3),         
        round(toplam_degisim_orani, 2), 
        round(fon_portfoye_katki, 2), 
        round(fon_net_kar_zarar, 2)
    ])

sutunlar = [
    'Fon Kodu', 'Fon Adı', 'Ağırlık (%)', 'Yatırılan Tutar (TL)', 
    'Giriş Fiyatı (TL)', 'Güncel Fiyat (TL)', 'Toplam Değişim (%)', 
    'Portföye Katkı (%)', 'Net Kâr/Zarar (TL)'
]
df = pd.DataFrame(rapor_data, columns=sutunlar)

genel_kar = float(toplam_guncel_deger - toplam_maliyet)
genel_degisim = float((genel_kar / toplam_maliyet) * 100)

toplam_satiri = pd.DataFrame([[
    'TOPLAM', 
    'Genel Portföy Durumu', 
    100.0, 
    round(toplam_maliyet, 2),
    None, 
    None, 
    round(genel_degisim, 2), 
    round(toplam_portfoye_katki, 2), 
    round(genel_kar, 2)
]], columns=sutunlar)

df = pd.concat([df, toplam_satiri], ignore_index=True)

excel_adi = f"BES_Raporu_{tarih_str}.xlsx"

# Pandas ile veriyi yazıp openpyxl ile grafik ekleme işlemi
with pd.ExcelWriter(excel_adi, engine='openpyxl') as writer:
    df.to_excel(writer, index=False, sheet_name='BES Takip')
    
    # Grafik motorunu çağırıyoruz
    workbook = writer.book
    worksheet = writer.sheets['BES Takip']
    
    # 1. GRAFİK: NET KÂR / ZARAR ÇUBUK GRAFİĞİ
    chart_bar = BarChart()
    chart_bar.type = "col"
    chart_bar.style = 10
    chart_bar.title = "Fon Bazlı Net Kâr / Zarar (TL)"
    chart_bar.y_axis.title = "TL Oranı"
    chart_bar.x_axis.title = "Fon Kodu"
    
    # Veri referansı (Net Kâr/Zarar sütunu olan 'I' sütunu, 1. satırdan 6. satıra kadar)
    data_bar = Reference(worksheet, min_col=9, min_row=1, max_row=6)
    # Kategori referansı (Fon Kodları olan 'A' sütunu)
    cats_bar = Reference(worksheet, min_col=1, min_row=2, max_row=6)
    
    chart_bar.add_data(data_bar, titles_from_data=True)
    chart_bar.set_categories(cats_bar)
    chart_bar.legend = None # Tek seri olduğu için lejantı gizle
    
    # Grafiği Excel'de A9 hücre konumunun altına yerleştir
    worksheet.add_chart(chart_bar, "A9")

print("Grafikli Excel Raporu başarıyla üretildi.")
