# Bibliopolis

Turn a literature collection into a city-state.

![A tiny city with its parts named: a house, a road, a branch road, the town hall and the ring road round it](docs/images/concept.svg)

*A tiny invented city with its parts named. An article is a house. A topic is a road, and a sub-topic is a branch road. The town hall is the root of the topic
tree. Articles that have no topic yet live on the ring road round the town hall.*

Every article is a house. Topics are roads that radiate from the town hall at the centre, and the tags of an article are the
residents of its house. The city grows as the collection grows.

**Status: early.** The city engine and its command line work, in both modes. A city can also be built by hand, one act at a time
(a world with its own commands: [docs/world.md](docs/world.md)). There is no viewer yet, no Zotero import and no
ready-made topic tree: you bring a library file and a topic tree (formats: [docs/format.md](docs/format.md)). This repository is the
open extraction of a private, self-use project.

## Set up

This takes a few minutes and needs no programming. You need Python 3.11 or newer and the files of this repository. Nothing else has to be installed: the
program uses only what comes with Python.

**1. Check Python, and install it if you need to.** Open a terminal (Windows: open the Start menu, type `cmd` and press Enter; Mac: open Terminal; Linux:
open your terminal program) and check the version:

```
python3 --version
```

If it says Python 3.11 or higher, go on to step 2. On Windows, type `py` instead of `python3` here and in every command on this page. If it says an older
version (a Mac may come with Python 3.9), or that the command is not found, install Python:

- Windows and Mac: download the installer from [python.org/downloads](https://www.python.org/downloads/) and run it. On a Mac you can use Homebrew instead:
  `brew install python`.
- Linux: python.org has no installer for it, so use your system's package manager. Many systems already have Python 3, so try the check above first. As
  examples, on Debian and Ubuntu: `sudo apt install python3`; on Fedora: `sudo dnf install python3`.

**2. Get the files.** If you have Git, run this:

```
git clone https://github.com/copper0722/bibliopolis-open.git
```

If you do not, open the repository on GitHub, press the green "Code" button, choose "Download ZIP" and unzip the file. Either way you get a folder.

**3. Open a terminal in that folder.** If you used `git clone`, type `cd bibliopolis-open` in the same terminal. Otherwise, on Windows open the folder in
File Explorer, click its address bar, type `cmd` and press Enter. On a Mac open Terminal, type `cd ` (with a space after it), drag the folder into the
window and press Enter. On Linux right-click in the folder and choose "Open in Terminal"; if your desktop has no such entry, open any terminal and type
`cd <path to the folder>`.

**4. Build a city and draw it.** Type these two commands, one after the other:

```
python3 -m bibliopolis build --library examples/library.json --tree examples/tree.json --mode grow --out city.json
python3 -m bibliopolis picture --city city.json --out city.svg
```

Each one prints a line when it is done:

```
wrote city.json: 600 houses on 23 roads, 15 on the ring road, 22 splits, 1 over (mode grow)
wrote city.svg: 41302 bytes
```

**5. Look at it.** Open `city.svg` in a web browser: drag the file onto a browser window, or right-click it and choose "Open with". You see the town hall
in the middle, the roads that go out from it, and a coloured house for each article. The picture is big (1800 pixels wide): if your browser shows only part
of it, zoom out with Ctrl and the minus key (Cmd and the minus key on a Mac). The example library is invented; to use your own, see "Try it" below.

Only the tests need an extra package, pytest (see Tests below). `build`, `picture` and `chronicle` need no packages.

## How a city grows

A city starts as a town hall with one road round it, the ring road, called Knowledge. Each new article becomes a house at once, and it is built on the ring road. There
is no other road until the ring road holds more than 40 houses. Then the largest group of at least 10 houses that share a sub-topic moves out and opens
the first road, which leaves the ring road. After that, any road that holds more than 40 houses opens a branch road for its own largest group in the same way.

![The example city in grow mode after 40, 41, 150 and 600 houses](docs/images/growth.svg)

*The example library (600 invented items) in `grow` mode, after 40, 41, 150 and 600 houses, on one frame. After 40 houses there is no road but the ring road: all 40
are on the ring road. House 41 opens the first road, and the orange houses are the ones that moved. Later splits add roads and branch roads.*

The town hall keeps a chronicle of every split. The command prints it, one sentence per entry (the first four here):

```
python3 -m bibliopolis build --library examples/library.json --tree examples/tree.json --mode grow --out city.json
python3 -m bibliopolis chronicle --city city.json --limit 4
```

```
house 41, 2019-06-26: Knowledge held 41 houses. Computing opens as a road with 15 of them; 26 stay.
house 62, 2019-10-15: Knowledge held 41 houses. Physical sciences opens as a road with 12 of them; 29 stay.
house 85, 2020-01-26: Knowledge held 41 houses. Life sciences opens as a road with 17 of them; 24 stay.
house 130, 2020-08-12: Computing held 41 houses. Systems opens as a road with 20 of them; 21 stay.
```

To see the city as it was at house 41, build it again with `--first 41` and draw it. The directions do not change: the plan reads the whole library before the
first house is built, so every road points the same way as in the full city. This is the same city at an earlier moment.

```
python3 -m bibliopolis build --library examples/library.json --tree examples/tree.json --mode grow --first 41 --out city-41.json
python3 -m bibliopolis picture --city city-41.json --out city-41.svg
```

## Two modes

- **Your library as a city (`mirror`).** Your topic tree (for Zotero, the collection tree) is the street plan: every topic an item is
  filed under is a road from the start, and so is every topic above one. An item stands once, at its deepest topic. Items arrive in the
  order you added them, so the growth of the city can be replayed. Items in no topic live on the ring road round the town hall. A road that
  holds more than 40 houses is marked as crowded.
- **A city from zero (`grow`, data-driven).** Houses arrive one at a time and the roads grow from the data:
  - The first houses live on the ring road round the town hall.
  - A road holds 10 to 40 houses directly.
  - When a road holds more than 40, the largest group of at least 10 of its houses that share a sub-topic moves out and opens a new
    road.
  - Every split is written into the town hall's chronicle, where it can be checked and repaired.

![The same 600 items as a mirror city and as a grow city](docs/images/modes.svg)

*The same 600 items in both modes, on one frame. Left, `mirror`: the topic tree is the street plan. Right, `grow`: the roads opened one by one as the houses
arrived.*

## Try it

With Python and the files in place (see Set up above), run these in the folder of the files:

```
python3 -m bibliopolis build --library examples/library.json --tree examples/tree.json --mode grow --out city.json
python3 -m bibliopolis build --library examples/library.json --tree examples/tree.json --mode mirror --out city-mirror.json
python3 -m bibliopolis picture --city city.json --out city.svg
```

The example is a synthetic library of 600 items on a tree of 80 topics, made by `examples/make_example.py`; every title, author and DOI
is invented. In `grow` mode the first road opens at the 41st item, one topic (Networks) holds more than 40 houses of its own and is
marked over, and the chain Humanities / History becomes one road. The `build` command says what it made:

```
wrote city.json: 600 houses on 23 roads, 15 on the ring road, 22 splits, 1 over (mode grow)
```

`city.json` holds the geometry and the structure of the city, not the titles: those stay in your library file. The same input gives the
same file, byte for byte. `picture` draws a city as one SVG file that opens in a browser, and `chronicle` prints what happened in it. Formats are in
[docs/format.md](docs/format.md), the rules in [docs/engine.md](docs/engine.md).

Your own files: a library `{"items": [...]}` in which every item has `id`, `title`, `authors`, `year`, `added_at`, `type`, `tags` and
`topics` (and, if you like, `doi`), and a tree `{"nodes": [{"id", "label", "parent"}, ...]}`. A wrong file is refused, with the place
of each problem. JSON Schema files are in `schema/`. The tree may also name a root bucket, `"bucket": "<id of a root node>"`, for what you have not sorted yet: it and what is below it get
no road, and an item filed only there stands on the ring road.

## Tests

Only the tests need a package that does not come with Python: pytest. (`build`, `picture` and `chronicle` need no packages at all.) Some systems, such as
Homebrew and Debian or Ubuntu, do not let `pip` install into their own Python, so make a virtual environment in the folder of the files first, put pytest into
it and run the tests with that environment's Python:

```
python3 -m venv .venv
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest
```

On Debian and Ubuntu, if the first line says that the environment could not be created, run `sudo apt install python3-venv` first. On Windows the
environment's Python is `.venv\Scripts\python`: make the environment with `py -m venv .venv`, then run `.venv\Scripts\python -m pip install pytest` and
`.venv\Scripts\python -m pytest`.

The pictures of this page are made by `examples/make_pictures.py` from the example. A test makes them again and compares them with the files in
`docs/images/` byte for byte, so they cannot go stale. After a change to the engine or the example, run `python3 examples/make_pictures.py` and commit
the result.

## Principles

- One article, one house. Only articles are buildings; the town hall is a plaza.
- No full text, abstracts, figures or media are stored: bibliographic metadata, your classification and your own notes only.
- Text and code only in Git; the one exception is PNG images directly under `docs/images/` (pixels only, at most 1 MiB each).

## License

[MIT](LICENSE)

---

# 文獻城邦

把收藏的文獻蓋成一座城邦。

![一座小城邦，標出房子、路、岔路、市政廳與環繞市政廳的環形大道](docs/images/concept.svg)

*一座虛構的小城邦，標出各個部分。一篇文獻是一棟房子，一個主題是一條路，子主題是岔路，市政廳是主題樹的根。還沒有主題的文獻，住在環繞市政廳的環形大道上。*

一篇文獻是一棟房子。主題是從市政廳往外放射的路，文獻的標籤是房子裡的居民。收藏越多，城邦越大。

**狀態：起步中。** 城邦引擎與命令列已經可以用，兩種模式都有。城邦也可以一步一步手工建造（另有一組自己的指令：[docs/world.md](docs/world.md)，英文）。目前還沒有檢視器，還不能直接匯入 Zotero，也沒有現成的主題樹：
你要自備文獻庫檔案與主題樹（格式見 [docs/format.md](docs/format.md)）。這個 repo 是一個私人自用專案的開源版。

## 安裝與設定

不需要會寫程式，幾分鐘就能完成。你需要兩樣東西：Python 3.11 或更新的版本，以及這個 repo 的檔案。其他東西都不用安裝：這個程式只用 Python 內建的功能。

**1. 檢查 Python，需要的話再安裝。** 開啟終端機（Windows：打開開始功能表，輸入 `cmd` 再按 Enter；Mac：開啟「終端機」；Linux：開啟你的終端機程式），檢查版本：

```
python3 --version
```

畫面如果顯示 Python 3.11 或更高的版本，就直接做第 2 步。Windows 請把這一頁每一行指令裡的 `python3` 改成 `py`。如果顯示的版本比較舊（有些 Mac 內建的是 Python 3.9），
或是說找不到這個指令，請先安裝 Python：

- Windows 與 Mac：到 [python.org/downloads](https://www.python.org/downloads/) 下載安裝程式並執行。Mac 也可以改用 Homebrew：`brew install python`。
- Linux：python.org 沒有提供 Linux 的安裝程式，請改用系統的套件管理員。很多系統本來就有 Python 3，所以先做上面的檢查。以下只是舉例：Debian、Ubuntu 用
  `sudo apt install python3`；Fedora 用 `sudo dnf install python3`。

**2. 取得檔案。** 如果你有安裝 Git，可以執行這一行：

```
git clone https://github.com/copper0722/bibliopolis-open.git
```

沒有 Git 的話，打開這個 repo 在 GitHub 上的頁面，按綠色的「Code」按鈕，選「Download ZIP」，再把下載的檔案解壓縮。兩種做法都會得到一個資料夾。

**3. 在那個資料夾裡開啟終端機。** 如果你用的是 `git clone`，在同一個終端機輸入 `cd bibliopolis-open` 就可以。否則，Windows 請用檔案總管打開資料夾，點一下上方的網址列，
輸入 `cmd` 再按 Enter；Mac 請開啟「終端機」，輸入 `cd `（後面留一個空格），把資料夾拖進視窗，再按 Enter；Linux 請在資料夾裡按右鍵，選「在終端機中開啟」；如果你的桌面沒有這個選項，就開啟任何一個終端機，輸入
`cd <path to the folder>`（把 `<path to the folder>` 換成那個資料夾的路徑）。

**4. 蓋一座城邦，再把它畫出來。** 依序輸入這兩行指令：

```
python3 -m bibliopolis build --library examples/library.json --tree examples/tree.json --mode grow --out city.json
python3 -m bibliopolis picture --city city.json --out city.svg
```

每一行做完，都會印出一行結果：

```
wrote city.json: 600 houses on 23 roads, 15 on the ring road, 22 splits, 1 over (mode grow)
wrote city.svg: 41302 bytes
```

**5. 看看成果。** 用瀏覽器打開 `city.svg`：把檔案拖進瀏覽器視窗，或對檔案按右鍵，選「開啟方式」。你會看到市政廳在中央，路從它往外延伸，每篇文獻是一棟上了色的房子。
這張圖很大（寬 1800 像素），如果瀏覽器只顯示一部分，請縮小畫面：按 Ctrl 加減號（Mac 按 Cmd 加減號）。範例文獻庫是虛構的；要用你自己的文獻庫，請看下面的「試試看」。

只有測試需要多裝一個套件 pytest（見下面的「測試」）；`build`、`picture`、`chronicle` 不需要任何套件。

## 城邦怎麼長大

一座城邦一開始只有市政廳，和環繞它的一條路：環形大道，名叫 Knowledge。每一篇新文獻立刻蓋成一棟房子，蓋在環形大道上。環形大道住滿 40 棟之前，沒有別的路。超過 40 棟時，
同一個子主題、至少 10 棟的最大一組房子搬出去，開出第一條路，離開環形大道。之後任何一條路超過 40 棟，就用同樣的方法，為它自己最大的一組房子開一條岔路。

![範例城邦在 grow 模式下，蓋到第 40、41、150、600 棟時的樣子](docs/images/growth.svg)

*範例文獻庫（600 筆虛構文獻）在 `grow` 模式下，蓋到第 40、41、150、600 棟時的樣子，四張圖用同一個畫面。蓋到第 40 棟時只有環形大道這一條路，40 棟全住在上面。
第 41 棟讓第一條路開出來，橘色是搬出去的房子。之後的分路陸續長出更多路與岔路。*

市政廳會記下每一次分路，寫成市政紀事。下面的指令把它印出來，一筆一句（這裡只列前四筆）：

```
python3 -m bibliopolis build --library examples/library.json --tree examples/tree.json --mode grow --out city.json
python3 -m bibliopolis chronicle --city city.json --limit 4
```

```
house 41, 2019-06-26: Knowledge held 41 houses. Computing opens as a road with 15 of them; 26 stay.
house 62, 2019-10-15: Knowledge held 41 houses. Physical sciences opens as a road with 12 of them; 29 stay.
house 85, 2020-01-26: Knowledge held 41 houses. Life sciences opens as a road with 17 of them; 24 stay.
house 130, 2020-08-12: Computing held 41 houses. Systems opens as a road with 20 of them; 21 stay.
```

想看蓋到第 41 棟時的城邦，加上 `--first 41` 再蓋一次，然後把它畫出來。路的方向不會變：規劃在蓋第一棟房子之前，就已經讀過整份文獻庫，所以每條路的方向都和完整城邦相同。這是同一座城邦在較早的時刻。

```
python3 -m bibliopolis build --library examples/library.json --tree examples/tree.json --mode grow --first 41 --out city-41.json
python3 -m bibliopolis picture --city city-41.json --out city-41.svg
```

## 兩種模式

- **把你的文獻庫變成城邦（`mirror`）。** 你的主題樹（用 Zotero 的話，就是 collection 樹）就是路網：文獻歸在哪些主題，那些主題一開始就是路，
  它們上面的主題也是。一篇文獻只蓋一棟房子，蓋在它最深的那個主題。文獻依加入的先後抵達，所以城市的成長可以回放。沒有主題的文獻，住在環繞市政廳的環形大道上。
  一條路住超過 40 棟，會被標成擁擠。
- **從零開始建城邦（`grow`，依資料長出來）。** 房子一棟一棟進來，路依資料自己長出來：
  - 最早的房子住在環繞市政廳的環形大道上。
  - 一條路直接住 10 到 40 棟。
  - 一條路超過 40 棟時，把同一個子主題、至少 10 棟的最大一組房子搬出去，開一條新路。
  - 每一次分路都記在市政廳的市政紀事裡，可以查，也可以修補。

![同樣的 600 筆文獻，蓋成 mirror 城邦與 grow 城邦](docs/images/modes.svg)

*同樣的 600 筆文獻，兩種模式，同一個畫面。左：`mirror`，主題樹就是路網。右：`grow`，路隨文獻抵達，一條一條開出來。*

## 試試看

照上面的「安裝與設定」準備好 Python 與檔案之後，在檔案所在的資料夾裡執行：

```
python3 -m bibliopolis build --library examples/library.json --tree examples/tree.json --mode grow --out city.json
python3 -m bibliopolis build --library examples/library.json --tree examples/tree.json --mode mirror --out city-mirror.json
python3 -m bibliopolis picture --city city.json --out city.svg
```

範例是一個合成的文獻庫：80 個主題、600 篇文獻，由 `examples/make_example.py` 產生，標題、作者與 DOI 都是虛構的。在 `grow` 模式下，
第 41 篇文獻讓第一條路開出來；有一個主題（Networks）自己就住了超過 40 棟，被標成超額；Humanities / History 這條單一路徑的主題鏈，合併成一條路。
`build` 指令會告訴你它蓋出了什麼：

```
wrote city.json: 600 houses on 23 roads, 15 on the ring road, 22 splits, 1 over (mode grow)
```

`city.json` 只放城邦的幾何與結構，不放標題；標題留在你自己的文獻庫檔案裡。相同的輸入會得到逐位元組相同的檔案。`picture` 把城邦畫成一個可以用瀏覽器開啟的 SVG 檔，
`chronicle` 印出城邦裡發生過的事。格式見 [docs/format.md](docs/format.md)，規則見 [docs/engine.md](docs/engine.md)（英文）。

用你自己的檔案：文獻庫 `{"items": [...]}`，每筆文獻要有 `id`、`title`、`authors`、`year`、`added_at`、`type`、`tags`、`topics`
（`doi` 可有可無）；主題樹 `{"nodes": [{"id", "label", "parent"}, ...]}`。檔案有誤時，指令會拒絕執行，並指出每個問題在哪裡。
`schema/` 裡有 JSON Schema 檔。主題樹也可以用 `"bucket": "<某個根節點的 id>"` 指定一個「還沒整理」的收納處：它和它底下的節點不會有路，只歸在那裡的文獻，房子會蓋在環路上。

## 測試

只有測試需要一個 Python 沒有內建的套件：pytest。（`build`、`picture`、`chronicle` 完全不需要任何套件。）有些系統（例如 Homebrew，以及 Debian、Ubuntu）不讓 `pip`
裝進系統自己的 Python，所以請先在檔案所在的資料夾裡建一個虛擬環境，把 pytest 裝進去，再用那個環境的 Python 跑測試：

```
python3 -m venv .venv
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest
```

在 Debian 和 Ubuntu 上，如果第一行說無法建立虛擬環境，請先執行 `sudo apt install python3-venv`。Windows 上，這個環境的 Python 在 `.venv\Scripts\python`：
用 `py -m venv .venv` 建立環境，再執行 `.venv\Scripts\python -m pip install pytest` 和 `.venv\Scripts\python -m pytest`。

這一頁的圖由 `examples/make_pictures.py` 從範例產生。測試會重新產生這些圖，和 `docs/images/` 裡的檔案逐位元組比對，所以圖不會過期。
改了引擎或範例之後，執行 `python3 examples/make_pictures.py`，再把結果提交。

## 原則

- 一篇文獻一棟房子。只有文獻是建築，市政廳是廣場。
- 不存全文、摘要、圖表或影音；只存書目資料、你的分類與你自己的筆記。
- Git 裡只有文字與程式；唯一的例外是直接放在 `docs/images/` 底下的 PNG 圖片（只含像素，每張不超過 1 MiB）。

## 授權

[MIT](LICENSE)
