WITH
last_period AS (
    SELECT MAX(TRIM(n7.period)) AS period
    FROM   nachisleniya n7
    WHERE  REGEXP_LIKE(TRIM(n7.period), '^\d{4}(0[1-9]|1[0-2])$')
),
tax_kbk AS (
    SELECT TRIM(k.kbk) AS kbk
    FROM   kbk_spr k
    WHERE  k.priznak_nalog = 'Y'
      AND  NOT EXISTS (SELECT 1
                       FROM   excluded_kbk e
                       WHERE  TRIM(e.kbk) = TRIM(k.kbk))
),
nach AS (
    SELECT n7.inn,
           SUM(NVL(n7.summa, 0)) AS nachisleno
    FROM   nachisleniya n7
    JOIN   tax_kbk t ON t.kbk = TRIM(n7.kbk)
    JOIN   last_period lp ON TRIM(n7.period) = lp.period
    GROUP  BY n7.inn
),
opl AS (
    SELECT p7.inn,
           SUM(NVL(p7.summa, 0)) AS oplacheno
    FROM   postupleniya p7
    JOIN   tax_kbk t ON t.kbk = TRIM(p7.kbk)
    JOIN   last_period lp ON TRIM(p7.period) = lp.period
    GROUP  BY p7.inn
),
calc_final AS (
    SELECT SUBSTR(n.inn, 1, 2)                       AS region_kod,
           n.inn,
           np.naim                                   AS naimenovanie,
           n.nachisleno,
           NVL(o.oplacheno, 0)                       AS oplacheno,
           n.nachisleno - NVL(o.oplacheno, 0)        AS nedoimka,
           RANK() OVER (PARTITION BY SUBSTR(n.inn, 1, 2)
                        ORDER BY n.nachisleno - NVL(o.oplacheno, 0) DESC) AS mesto
    FROM   nach n
    LEFT   JOIN opl o                  ON o.inn  = n.inn
    LEFT   JOIN nalogoplatelshchiki np ON np.inn = n.inn
    WHERE  n.nachisleno - NVL(o.oplacheno, 0) > 0
)
SELECT region_kod,
       inn,
       naimenovanie,
       nachisleno,
       oplacheno,
       nedoimka,
       mesto
FROM   calc_final
WHERE  mesto <= 5
ORDER  BY region_kod, mesto, inn;