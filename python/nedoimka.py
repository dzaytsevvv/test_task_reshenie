import sys
from pathlib import Path

import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.float_format", lambda x: f"{x:,.2f}".replace(",", " "))

BASE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent

FILES = {
    "nach": "nachisleniya_raw.csv",
    "post": "postupleniya_raw.csv",
    "reg": "regiony.csv",
    "kbk": "kbk_ref.csv",
}

# Возможные названия колонок в выгрузках -> единое имя.
# (Выгрузки «живые»: регистр, пробелы, синонимы.)
COL_ALIASES = {
    "inn": ["inn", "инн"],
    "kbk": ["kbk", "кбк"],
    "summa": ["summa", "summa_nachisleno", "summa_oplacheno", "сумма", "sum", "amount"],
    "period": ["period", "период"],
    "data_oper": ["data_oper", "data_operacii", "дата_операции", "date_oper"],
    "data_plat": ["data_plat", "data_platezha", "дата_платежа", "date_plat"],
    "region_kod": ["kod", "region_kod", "kod_regiona", "код", "код_региона", "region_code"],
    "region_name": ["region_name", "region_naim", "naimenovanie", "name", "наименование", "регион"],
    "fed_okrug": ["fed_okrug", "federalnyy_okrug", "fo", "федеральный_округ", "фо", "okrug"],
    "priznak_nalog": ["priznak_nalog", "nalog", "признак", "налоговый"],
}

QC = []  # строки отчёта о качестве данных


def qc(table, check, value):
    QC.append({"таблица": table, "проверка": check, "значение": value})


# ---------------------------------------------------------------- D1: загрузка
def read_csv_any(path: Path, name: str = None) -> pd.DataFrame:
    """Читает CSV с «;», всё как строки; пробует utf-8 (с BOM) и cp1251."""
    for enc in ("utf-8-sig", "cp1251"):
        try:
            df = pd.read_csv(path, sep=";", dtype=str, encoding=enc,
                             keep_default_na=False, skipinitialspace=True)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"Не удалось определить кодировку {path}")
    # нормализуем заголовки и находим колонки по синонимам
    df.columns = [re.sub(r"\s+", "_", c.strip().lower()) for c in df.columns]
    rename = {}
    for std, aliases in COL_ALIASES.items():
        for c in df.columns:
            if c in aliases and std not in rename.values():
                rename[c] = std
    df = df.rename(columns=rename)
    # trim + схлопывание повторных пробелов во всех текстовых полях
    raw = df.copy()
    for c in df.columns:
        df[c] = (df[c].str.replace(" ", " ", regex=False)
                      .str.strip()
                      .str.replace(r"\s+", " ", regex=True))
    if name:
        fixed = (raw != df)
        qc(name, "ячеек с лишними пробелами (исправлено)", int(fixed.values.sum()))
        if "kbk" in df.columns:
            qc(name, "  из них в КБК", int(fixed["kbk"].sum()))
    return df


def to_number(s: pd.Series) -> pd.Series:
    """'1 234 567,89' / '1234,5' / ' -12,00 ' -> float; мусор -> NaN."""
    cleaned = (s.fillna("")
                .str.replace(r"[\s  ]", "", regex=True)  # пробелы-разряды
                .str.replace(",", ".", regex=False))               # запятая-десятичная
    return pd.to_numeric(cleaned, errors="coerce")


def clean_money_table(df: pd.DataFrame, name: str, date_col: str) -> pd.DataFrame:
    n0 = len(df)
    qc(name, "строк загружено", n0)

    raw_sum = df["summa"]
    df["summa"] = to_number(raw_sum)
    empty = raw_sum.eq("")
    garbage = df["summa"].isna() & ~empty
    qc(name, "пустых сумм (-> 0)", int(empty.sum()))
    qc(name, "нечисловых сумм (-> 0)", int(garbage.sum()))
    if garbage.any():
        qc(name, "  примеры мусора", ", ".join(raw_sum[garbage].unique()[:5]))
    df["summa"] = df["summa"].fillna(0.0)
    qc(name, "отрицательных сумм", int((df["summa"] < 0).sum()))
    qc(name, "нулевых сумм", int((df["summa"] == 0).sum()))

    # ИНН: только цифры, 10 знаков
    df["inn"] = df["inn"].str.replace(r"\D", "", regex=True)
    df.loc[df["inn"].str.len() == 9, "inn"] = df["inn"].str.zfill(10)  # потерянный ведущий 0 (Excel)
    bad_inn = df["inn"].str.len() != 10
    qc(name, "ИНН не из 10 цифр", int(bad_inn.sum()))
    df["kbk"] = df["kbk"].str.replace(" ", "", regex=False)

    if date_col in df.columns:
        d = pd.to_datetime(df[date_col], format="%d.%m.%Y", errors="coerce")
        d = d.fillna(pd.to_datetime(df[date_col], format="%Y-%m-%d", errors="coerce"))
        qc(name, f"нераспознанных дат {date_col}", int((d.isna() & df[date_col].ne("")).sum()))
        df[date_col] = d

    dup = df.duplicated(keep="first")
    qc(name, "дублей строк (удалено)", int(dup.sum()))
    df = df[~dup].copy()
    if "id" in df.columns:  # контроль: после удаления полных дублей id должен быть уникален
        qc(name, "неуникальных id после очистки", int(df["id"].duplicated().sum()))
    qc(name, "строк после очистки", len(df))
    return df


def load():
    nach = clean_money_table(read_csv_any(BASE / FILES["nach"], "начисления"), "начисления", "data_oper")
    post = clean_money_table(read_csv_any(BASE / FILES["post"], "поступления"), "поступления", "data_plat")

    reg = read_csv_any(BASE / FILES["reg"], "регионы")
    reg["region_kod"] = reg["region_kod"].str.zfill(2)
    # регистр в справочнике «грязный» (МОСКОВСКАЯ ОБЛАСТЬ) -> приводим к единому виду
    reg["region_name"] = reg["region_name"].map(lambda x: x.capitalize() if x.isupper() else x)
    reg = reg.drop_duplicates("region_kod")

    kbk = read_csv_any(BASE / FILES["kbk"])
    kbk["kbk"] = kbk["kbk"].str.replace(" ", "", regex=False)
    kbk["priznak_nalog"] = kbk["priznak_nalog"].str.upper().str.strip()
    kbk = kbk.drop_duplicates("kbk")
    return nach, post, reg, kbk


# ---------------------------------------------------------------- D2: расчёт
def calc(nach, post, reg, kbk):
    tax_kbk = set(kbk.loc[kbk["priznak_nalog"] == "Y", "kbk"])

    for name, df in (("начисления", nach), ("поступления", post)):
        unknown = ~df["kbk"].isin(kbk["kbk"])
        qc(name, "КБК нет в справочнике (исключены)", int(unknown.sum()))

    n_tax = nach[nach["kbk"].isin(tax_kbk)]
    p_tax = post[post["kbk"].isin(tax_kbk)]

    # Агрегируем каждую сторону ОТДЕЛЬНО, потом outer-join агрегатов (без fan-out)
    agg_n = n_tax.groupby("inn", as_index=False)["summa"].sum().rename(columns={"summa": "nachisleno"})
    agg_p = p_tax.groupby("inn", as_index=False)["summa"].sum().rename(columns={"summa": "oplacheno"})
    df = agg_n.merge(agg_p, on="inn", how="outer").fillna({"nachisleno": 0.0, "oplacheno": 0.0})
    df["nedoimka"] = (df["nachisleno"] - df["oplacheno"]).round(2)

    df["region_kod"] = df["inn"].str[:2]
    df = df.merge(reg[["region_kod", "region_name", "fed_okrug"]], on="region_kod", how="left")
    qc("расчёт", "ИНН с регионом не из справочника", int(df["region_name"].isna().sum()))
    qc("расчёт", "ИНН только с поступлениями (без начислений)", int((df["nachisleno"] == 0).sum()))
    qc("расчёт", "ИНН без поступлений", int((df["oplacheno"] == 0).sum()))
    return df.sort_values("nedoimka", ascending=False).reset_index(drop=True)


def main():
    nach, post, reg, kbk = load()
    by_inn = calc(nach, post, reg, kbk)

    # ТОП-5 регионов: недоимка = сумма положительных недоимок ИНН
    by_inn["dolg"] = by_inn["nedoimka"].clip(lower=0)
    df_result = (by_inn.groupby(["region_kod", "region_name", "fed_okrug"], dropna=False, as_index=False)
                       .agg(nedoimka=("dolg", "sum"),
                            saldo=("nedoimka", "sum"),
                            dolzhnikov=("dolg", lambda s: int((s > 0).sum())))
                       .sort_values("nedoimka", ascending=False)
                       .head(5)
                       .reset_index(drop=True))
    df_result.index = df_result.index + 1

    # D3: переплата
    pereplata = (by_inn[by_inn["nedoimka"] < 0]
                 .assign(pereplata=lambda d: -d["nedoimka"])
                 [["inn", "region_kod", "region_name", "nachisleno", "oplacheno", "pereplata"]]
                 .sort_values("pereplata", ascending=False)
                 .reset_index(drop=True))
    pereplata.index = pereplata.index + 1

    print("=" * 90)
    print("КОНТРОЛЬ КАЧЕСТВА ДАННЫХ")
    print("=" * 90)
    print(pd.DataFrame(QC).to_string(index=False))

    print("\n" + "=" * 90)
    print("D2. Недоимка по налогоплательщикам (налоговые КБК), первые 10 из", len(by_inn))
    print("=" * 90)
    print(by_inn[["inn", "region_kod", "nachisleno", "oplacheno", "nedoimka"]].head(10).to_string(index=False))

    print("\n" + "=" * 90)
    print("D2. ТОП-5 регионов по суммарной недоимке (df_result)")
    print("=" * 90)
    print(df_result.to_string())

    print("\n" + "=" * 90)
    print(f"D3. Переплата (оплачено > начислено): {len(pereplata)} НП, "
          f"сумма {pereplata['pereplata'].sum():,.2f}".replace(",", " "))
    print("=" * 90)
    print(pereplata.to_string() if len(pereplata) else "нет")

    # Сверка: итог недоимки = начислено - оплачено (контрольная сумма)
    total = by_inn["nachisleno"].sum() - by_inn["oplacheno"].sum()
    assert abs(total - by_inn["nedoimka"].sum()) < 0.01, "контрольная сумма не сошлась"
    print(f"\nКонтроль: начислено {by_inn['nachisleno'].sum():,.2f} − оплачено "
          f"{by_inn['oplacheno'].sum():,.2f} = сальдо {total:,.2f}".replace(",", " "))

    out = BASE / "result"
    out.mkdir(exist_ok=True)
    by_inn.drop(columns="dolg").to_csv(out / "nedoimka_po_inn.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
    df_result.to_csv(out / "top5_regionov.csv", sep=";", decimal=",", encoding="utf-8-sig")
    pereplata.to_csv(out / "pereplata.csv", sep=";", decimal=",", encoding="utf-8-sig")
    return df_result


if __name__ == "__main__":
    df_result = main()
