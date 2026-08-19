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

tarih_str = datetime.now().strftime('%Y-%m-%d')
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
    
    rapor_data.append([
        kod, info['ad'], float(info['agirlik'] * 100), round(fon_maliyeti, 3),
        round(giris_fiy, 3), round(guncel_fiy, 3), round(toplam_degisim_orani, 3), 
        round(fon_portfoye_katki, 3), round(fon_net_kar_zarar, 3)
    ])

sutunlar = [
    'Fon Kodu', 'Fon Adi', 'Agirlik (%)', 'Yatirilan Tutar (TL)', 
    'Giris Fiyati (TL)', 'Guncel Fiyat (TL)', 'Toplam Degisim (%)', 
    'Portfoye Katki (%)', 'Net Kar/Zarar (TL)'
]
df = pd.DataFrame(rapor_data, columns=sutunlar)

genel_kar = float(toplam_guncel_deger - toplam_maliyet)
dogru_genel_degisim = float((genel_kar / toplam_maliyet) * 100)

toplam_satiri = pd.DataFrame([[
    'TOPLAM', 'Genel Portfoy Durumu', 100.0, round(toplam_maliyet, 3),
    0.000, 0.000, round(dogru_genel_degisim, 3), round(toplam_portfoye_katki, 3), round(genel_kar, 3)
]], columns=sutunlar)

df = pd.concat([df, toplam_satiri], ignore_index=True)

excel_adi = f"BES_Raporu_{tarih_str}.xlsx"
df.to_excel(excel_adi, index=False)
print("Excel basariyla diske yazildi.")
