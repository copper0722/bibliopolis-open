# Bibliopolis

Turn a literature collection into a city-state.

Every article is a house. Topics are roads that radiate from the town hall at the centre, and the tags of an article are the
residents of its house. The city grows as the collection grows.

**Status: early.** This repository is the open extraction of a private, self-use project. It is being filled step by step and
is not usable yet.

## Two modes (planned)

- **Your Zotero library as a city.** Your collection tree becomes the street plan. Items arrive in the order you added them, so
  the growth of the city can be replayed. Items in no collection live underground, below the town hall.
- **A city from zero (data-driven).** Houses arrive one at a time and the roads grow from the data:
  - The first houses live underground, below the town hall.
  - A road holds 10 to 40 houses directly.
  - When a road holds more than 40, the largest group of at least 10 of its houses that share a sub-topic moves out and opens a new
    road.
  - Every split is written into the town hall's chronicle, where it can be checked and repaired.

## Principles

- One article, one house. Only articles are buildings; the town hall is a plaza.
- No full text, abstracts, figures or media are stored: bibliographic metadata, your classification and your own notes only.
- Text and code only in Git; no binary assets.

## License

[MIT](LICENSE)

---

# 文獻城邦

把收藏的文獻蓋成一座城邦。

一篇文獻是一棟房子。主題是從市政廳往外放射的路，文獻的標籤是房子裡的居民。收藏越多，城邦越大。

**狀態：起步中。** 這個 repo 是一個私人自用專案的開源版，正在逐步搬入，目前還不能用。

## 兩種模式（規劃中）

- **把你的 Zotero 變成城邦。** 你的 collection 樹就是路網。文獻依加入 Zotero 的先後抵達，所以城市的成長可以回放。沒有放進任何
  collection 的文獻，住在市政廳正下方的地底。
- **從零開始建城邦（依資料長出來）。** 房子一棟一棟進來，路依資料自己長出來：
  - 最早的房子住在市政廳正下方的地底。
  - 一條路直接住 10 到 40 棟。
  - 一條路超過 40 棟時，把同一個子主題、至少 10 棟的最大一組房子搬出去，開一條新路。
  - 每一次分路都記在市政廳的市政紀事裡，可以查，也可以修補。

## 原則

- 一篇文獻一棟房子。只有文獻是建築，市政廳是廣場。
- 不存全文、摘要、圖表或影音；只存書目資料、你的分類與你自己的筆記。
- Git 裡只有文字與程式，沒有二進位素材。

## 授權

[MIT](LICENSE)
