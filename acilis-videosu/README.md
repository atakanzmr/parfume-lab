# Açılış videosu (intro.mp4)

Uygulama açılırken oynayan 7 saniyelik videonun kaynakları. 3D sahne Blender (Cycles) ile render edilir. Duman, erlenin çözülmesi ve logonun belirmesi Python ile birleştirilir.

## Dosyalar

- `scene.py`: 3D sahne. Erlen, sıvı, ölçek çizgileri, pipet, damlalar, zemin, ışıklar ve kamera burada.
- `anim.py`: Hareket. Damlanın oluşup düşmesi, sıçrama ve halkalar, kabarcıklar, pipetin çekilmesi. Sabit plakayı bir kez, değişen bölgeleri kare kare render eder (`frames/`).
- `comp.py`: Birleştirme. Sıvının parlaması, altın duman (akışkan simülasyonu), parıltılar, erlenin çözülmesi, logonun belirmesi ve zemin yansıması (`out/`).
- `post.py`: Parlama, kenar kararması ve film greni.
- `logo-kaynak.png`: Logo görseli.

## Yeniden üretmek

Gerekenler: Python 3.13 (bpy 5.3 bu sürümü ister) ve ffmpeg.

```
pip install bpy numpy scipy opencv-python pillow
python anim.py all     # 3D kareler: 2 çekirdekte yaklaşık 1 saat, var olan kareleri atlar
python comp.py all     # 216 kare: yaklaşık 1 dakika
ffmpeg -framerate 30 -i out/%04d.png -c:v libx264 -preset slow -crf 19 -profile:v high -level 4.0 -pix_fmt yuv420p -movflags +faststart -an intro.mp4
```

Çıkan `intro.mp4` repo köküne kopyalanır. Telefonlar yeni videoyu alsın diye `sw.js` içindeki `VERSION` bir artırılır.

## Neyi nereden değiştirirsin

- **Zamanlama (saniye):** `comp.py` başındaki değerler.
  - `T_GLOW`: sıvının parlaması
  - `T_SMOKE`: ağızdan çıkan duman
  - `T_DIS`: erlenin çözülmesi
  - `T_EDGE` ve `T_FILL`: logonun belirmesi
  - `T_CLEAR`: dumanın dağılması
- **Damlanın zamanlaması:** `anim.py` içindeki `F_DETACH` (kopma) ve `F_IMPACT` (çarpma). Bunlar kare numarasıdır, 30 kare 1 saniye eder.
- **Sıvının rengi ve parlaklığı:** `scene.py` içinde `liquid_mat('sivi', ...)` ve `GLOW`.
- **Dumanın rengi:** `comp.py` içinde `smoke_rgb`.
- **Logonun yeri ve boyu:** `comp.py` içinde `prep_static` (`560 / 923` ve `500` değerleri).

3D tarafında bir şey değiştirirsen `frames/` klasörünü silip `anim.py all` komutunu yeniden çalıştır. Yalnızca birleştirmeyi değiştirdiysen `comp.py all` yeter.
