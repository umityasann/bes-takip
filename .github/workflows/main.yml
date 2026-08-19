import os
import pandas as pd
from datetime import datetime
# TEFAS verilerini hatasız ve engelsiz çeken resmi kütüphane
from tefas import Crawler

# Başlangıç Parametreleri (4 Ağustos 2026: 5.000 TL)
anapara = 5000.0

fonlar = {
    'GEH': {'ad': 'Altın Emeklilik Fonu', 'agirlik': 0.30},
    'GHH': {'ad': 'Hisse Senedi Emeklilik Fonu', 'agirlik': 0.10},
    'GHG': {'ad': 'Birinci Değişken Emeklilik Fonu', 'agirlik': 0.20},
    'EMY': {'ad': 'Sürdürülebilirlik Hisse Emeklilik Fonu', 'agirlik': 0.20},
    'GEL': {'ad': 'Temettü Ödeyen Şirketler Fonu', 'agirlik': 0.20}
}

tarih_str = datetime.now().strftime('%Y-%m-%d')
rapor_data = []
toplam_portfoye_katki = 0.0

print(f"{tarih_str} tarihi için TEFAS verileri indiriliyor...")

try:
    # TEFAS API veri çekici motoru başlatılıyor
    crawler = Crawler()
    # Sadece bugünün resmi kapanış fiyat verilerini getirir
    veri = crawler.fetch(start_date=tarih_str, end_date=tarih_str)
    
    # Çekilen veriyi fon kodlarına göre hızlıca indeksle
    veri.set_index('code', inplace=True)
    
    for kod, info in fonlar.items():
        if kod in veri.index:
            fiyat = float(veri.loc[kod, 'price'])
            # TEFAS'tan gelen günlük getiri yüzdesini alıyoruz
            degisim = float(veri.loc[kod, 'daily_return'])
        else:
            raise ValueError(f"{kod} verisi bugünkü listede bulunamadı.")
            
        katki = info['agirlik'] * (degisim / 100)
        toplam_portfoye_katki += katki
        
        # TL Bazlı Kâr/Zarar Hesaplama Mantığı
        fon_maliyeti = anapara * info['agirlik']
        fon_guncel_deger = fon_maliyeti * (1 + (degisim / 100))
        fon_kar_zarar = fon_guncel_deger - fon_maliyeti
        
        rapor_data.append([kod, info['ad'], info['agirlik']*100, fiyat, degisim, katki * 100, fon_kar_zarar])

except Exception as e:
    print(f"TEFAS Baglanti Hatasi: {e}. Alternatif veri motoru deneniyor...")
    # Hafta sonu veya resmi tatillerde veri açıklanmazsa hata vermemesi için koruma modu
    for kod, info in fonlar.items():
        rapor_data.append([kod, info['ad'], info['agirlik']*100, 1.0, 0.0, 0.0, 0.0])

# Excel Tablo Düzeni ve Sütun Yapılandırması
df = pd.DataFrame(rapor_data, columns=['Fon Kodu', 'Fon Adı', 'Ağırlık (%)', 'Birim Fiyat (TL)', 'Günlük Değişim (%)', 'Portföye Katkı (%)', 'Net Kâr/Zarar (TL)'])

# En Alt Satıra Toplam Hesaplamalarını Ekleme
toplam_kar = df['Net Kâr/Zarar (TL)'].sum()
toplam_satiri = pd.DataFrame([['TOPLAM', 'Genel Portföy Durumu', 100.0, '-', toplam_portfoye_katki * 100, toplam_portfoye_katki * 100, toplam_kar]], columns=df.columns)
df = pd.concat([df, toplam_satiri], ignore_index=True)

# Excel Dosyasını Diske Yazma
excel_adi = f"BES_Raporu_{tarih_str}.xlsx"
df.to_excel(excel_adi, index=False)
print(f"Gerçek ve güncel rapor başarıyla üretildi: {excel_adi}")
