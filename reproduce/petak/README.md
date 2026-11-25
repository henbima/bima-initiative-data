# Detail geografis DAS Rontu

`build.py` menghitung perubahan per petak UTM sepanjang 1.000 m. Nomor petak terdiri dari easting dan northing (km) sudut barat daya. Gunakan `index.json` untuk batas petak, titik tengah dan titik referensi GeoNames terdekat. Nama tempat adalah acuan posisi titik tengah petak. Lokasi spesifik `topLoss.x/y` dan `topLoss.lon/lat` adalah pusat piksel yang benar-benar beralih keluar dari kelas yang dipantau dan terdekat dengan rata-rata koordinat piksel keluar di petak.

Definisi kelas awal dan akhir bergantung pada seri. Persentase keluar untuk petak harus menggunakan `loss/start` bila membahas proporsi tutupan awal. Ringkasan basin menjumlahkan semua 317 petak yang beririsan (jumlah petak bergantung pada grid sumber). Ranking memakai luas keluar bruto. Sel pinggir dibatasi oleh batas studi dan hanya piksel yang bisa dibandingkan pada kedua tahun yang masuk perhitungan.

## Menjalankan ulang

Memerlukan Python, numpy, pyproj dan Pillow. Gunakan `references.tsv` untuk mereproduksi label jarak dan arah. Ini merupakan potongan data Indonesia dari GeoNames (CC BY 4.0) untuk titik berpenduduk di sekitar wilayah analisis. [Sumber GeoNames](https://download.geonames.org/export/dump/ID.zip).

```text
python build.py --data PATH_DATA_SERI --gazetteer references.tsv --out OUTPUT
python verify.py PATH_DATA_SERI OUTPUT
```

## Isi berkas

- `index.json` berisi definisi grid, luas piksel dalam hektare, sumber, dan daftar berkas per tahun awal.
- `TAHUN_AWAL.json` memetakan tahun akhir ke daftar 10 petak keluar terbesar, komposisi kelas tujuan seluruh wilayah, dan penanda waktu pengamatan.
- `TAHUN_AWAL-grid.csv.zip` menyediakan hitungan per petak untuk semua pasangan dengan tahun awal tersebut. Hitungan adalah piksel dari seri terkait.
- `observedChangeWindows` adalah daftar triplet [tahun pantauan terakhir dalam kelas awal, tahun pertama rangkaian pantauan di luar kelas awal yang bertahan sampai tahun akhir, jumlah piksel]. Kedua nilai tahun merujuk pada dua pengamatan berurutan, yang bisa berjarak beberapa tahun. Jika observasi antara keduanya tidak valid, interval dicatat [null, null]. Sebagian piksel pernah keluar dan muncul kembali pada pengamatan lain. Produk klasifikasi memberi indikasi waktu perubahan yang tampak.
- `lastTwoNonTree` menghitung bagian dari piksel keluar yang sudah berada di luar kelas awal pada tahun kalender sebelumnya. `previousValidLoss` adalah jumlah piksel keluar yang memiliki observasi valid tahun sebelumnya. Keduanya bernilai null jika tahun sebelumnya sama dengan tahun awal atau tidak tersedia.

