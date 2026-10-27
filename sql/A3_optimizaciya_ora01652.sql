WITH calc_final AS (
    SELECT SUBSTR(n7.inn, 1, 2)  AS region_kod,
           n7.period,
           SUM(n7.summa)         AS region_sum,
           COUNT(DISTINCT n7.inn) AS cnt_inn
    FROM   nachisleniya n7
    WHERE  n7.period >= '202401'
    GROUP  BY SUBSTR(n7.inn, 1, 2), n7.period
)
SELECT region_kod, period, region_sum, cnt_inn
FROM   calc_final
ORDER  BY region_kod, period;