# Bima Initiative · data observatorium
Seri tahunan 10 m untuk wilayah analisis DAS Rontu di Bima. Setiap PNG merekam kode kelas asli dengan grid yang dijelaskan dalam `data/manifest.json`. Statistik luas dihitung pada piksel yang valid bersama, 0,01 ha per piksel.

Peta memakai produk Impact Observatory, Microsoft, dan Esri, dengan atribusi dan tautan lisensi di manifest. [Arsip sumber](https://registry.opendata.aws/io-lulc/). Geometri kerja merujuk pada fitur DAS420446. Pemeriksaan terhadap peta lokal, sumber, dan perbedaan luas terdapat pada `boundary-validation.json`. Lisensi data tutupan lahan berlaku khusus untuk produk tersebut.

## Pembaruan
Workflow memeriksa arsip pada awal setiap bulan, pukul 09.17 WITA. Jika ETag sumber, tahun, metode, atau batas berubah, workflow menghitung ulang seri dan memvalidasi hasil. Satu push memublikasikan data dan penanda revisi. Jika proses gagal, penanda rilis tetap menunjuk ke hasil terakhir. Situs membaca penanda lalu memuat data dari commit yang ditunjuk. Untuk menjalankan pemeriksaan, gunakan `pip install -r requirements.txt` dan `python update.py`.

CSV pada aplikasi dan ringkasan JSON menggunakan luas valid yang sama, tidak termasuk piksel berawan atau kosong. Kelas pohon mencakup tutupan vegetasi berpohon dan digunakan sebagai indikasi perubahan lanskap.
