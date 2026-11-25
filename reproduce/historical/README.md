# Arsip historis tutupan lahan DAS Rontu

Arsip berisi hasil GLC_FCS30D v2 yang dipublikasikan Liangyun Liu, Xiao Zhang, dan Zhehua Li melalui Zenodo pada 2025. Hak penggunaan dan atribusi mengikuti CC BY 4.0. [Sumber data](https://zenodo.org/records/15063683) · [Artikel metode](https://essd.copernicus.org/articles/16/1353/2024/)

## Menghasilkan ulang data

Jalankan dengan Python 3 dan dependensi `requests rasterio numpy Pillow pyproj`, dari direktori yang memuat skrip ini.

```sh
python source.py
python build.py --boundary /path/to/klhk-das420446.geojson
python verify.py
```

Skrip pengambilan hanya mengunduh dua anggota ZIP yang mencakup DAS Rontu, memakai HTTP Range dan memvalidasi CRC. Nama ZIP mencantumkan E110–E115 karena ia memuat ubin dengan sudut kiri atas E110 dan E115. Ubin yang dipakai adalah E115S5. Skrip pengolahan menyimpan SHA-256 tiap berkas asli, nomor band, dan checksum PNG pada manifest.

## Arti angka dan waktu

Setiap piksel hasil berukuran 30 × 30 m pada grid UTM 50S. Kode disalin dari pusat piksel terdekat pada raster geografis asli. Hanya piksel yang pusatnya di dalam poligon DAS dengan kode sumber DAS420446 dihitung. Area bersama yang valid menjadi dasar agregasi per pasangan tahun. Pengamatan 1985, 1990, dan 1995 menggabungkan citra dari sekitar dua tahun sebelum dan sesudah tahun tengah, sesuai artikel metode. Arsip memuat kelas tahunan untuk 2000–2022.

Pengelompokan hutan mengikuti kode 51, 52, 61, 62, 71, 72, 81, 82, 91, dan 92 pada legenda GLC. Kelas pertanian pohon atau perdu, mangrove, dan rawa dihitung dalam kelasnya sendiri. “Vegetasi jarang” mengikuti kode 150 dengan fraksi tutupan vegetasi di bawah 15%. Inferensi jenis komoditas atau legalitas pembukaan memerlukan bukti tambahan.

Jangan menghitung perubahan dengan mengurangkan angka GLC dari angka Esri. Misalnya pada 2017 kedua produk memberi luas berbeda di DAS yang sama karena kelas, metode pengolahan, dan ukuran piksel berbeda. Hitung tren di dalam masing-masing seri.
