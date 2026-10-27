WITH
excl AS (
    SELECT DISTINCT TRIM(e.kbk) AS kbk
    FROM   excluded_kbk e
    WHERE  e.kbk IS NOT NULL
),
nach AS (
    SELECT n7.inn, SUM(NVL(n7.summa, 0)) AS nachisleno
    FROM   nachisleniya n7
    WHERE  NOT EXISTS (SELECT 1 FROM excl x WHERE x.kbk = TRIM(n7.kbk))
    GROUP  BY n7.inn
),
opl AS (
    SELECT p7.inn, SUM(NVL(p7.summa, 0)) AS oplacheno
    FROM   postupleniya p7
    WHERE  NOT EXISTS (SELECT 1 FROM excl x WHERE x.kbk = TRIM(p7.kbk))
    GROUP  BY p7.inn
),
calc_final AS (
    SELECT COALESCE(n.inn, o.inn)                    AS inn,
           NVL(n.nachisleno, 0)                      AS nachisleno,
           NVL(o.oplacheno, 0)                       AS oplacheno,
           NVL(n.nachisleno, 0) - NVL(o.oplacheno, 0) AS nedoimka
    FROM   nach n
    FULL   OUTER JOIN opl o ON o.inn = n.inn
)
SELECT inn, nachisleno, oplacheno, nedoimka
FROM   calc_final
ORDER  BY nedoimka DESC;
