-- Reconstructs the flat netflix_titles.csv shape from the normalized
-- `movies` schema (see src/app/scripts/import_netflix_titles.py for the DDL).
--
-- Output columns match the CSV header exactly:
--   show_id,type,title,director,cast,country,date_added,release_year,
--   rating,duration,listed_in,description
--
-- Multi-valued columns (director, cast, country, listed_in) are rebuilt via
-- STRING_AGG over their junction tables. Note: the junction tables don't
-- preserve original ordering, so aggregated values come back alphabetized
-- rather than in the CSV's original order.

WITH directors_agg AS (
    SELECT td.show_id,
           STRING_AGG(d.name, ', ' ORDER BY d.name) AS director
    FROM movies.title_directors td
    JOIN movies.directors d ON d.id = td.director_id
    GROUP BY td.show_id
),
cast_agg AS (
    SELECT tc.show_id,
           STRING_AGG(cm.name, ', ' ORDER BY cm.name) AS cast
    FROM movies.title_cast tc
    JOIN movies.cast_members cm ON cm.id = tc.cast_member_id
    GROUP BY tc.show_id
),
countries_agg AS (
    SELECT tco.show_id,
           STRING_AGG(c.name, ', ' ORDER BY c.name) AS country
    FROM movies.title_countries tco
    JOIN movies.countries c ON c.id = tco.country_id
    GROUP BY tco.show_id
),
genres_agg AS (
    SELECT tg.show_id,
           STRING_AGG(g.name, ', ' ORDER BY g.name) AS listed_in
    FROM movies.title_genres tg
    JOIN movies.genres g ON g.id = tg.genre_id
    GROUP BY tg.show_id
)
SELECT
    t.show_id,
    ct.name AS type,
    t.title,
    da.director,
    ca.cast,
    coa.country,
    TO_CHAR(t.date_added, 'FMMonth FMDD, YYYY') AS date_added,
    t.release_year,
    r.code AS rating,
    CASE
        WHEN t.duration_unit = 'min'    THEN t.duration_value || ' min'
        WHEN t.duration_unit = 'season' THEN t.duration_value || ' Season'
             || CASE WHEN t.duration_value = 1 THEN '' ELSE 's' END
        ELSE NULL
    END AS duration,
    ga.listed_in,
    t.description
FROM movies.titles t
JOIN movies.content_types ct ON ct.id = t.type_id
LEFT JOIN movies.ratings r        ON r.id   = t.rating_id
LEFT JOIN directors_agg da        ON da.show_id  = t.show_id
LEFT JOIN cast_agg ca              ON ca.show_id  = t.show_id
LEFT JOIN countries_agg coa        ON coa.show_id = t.show_id
LEFT JOIN genres_agg ga            ON ga.show_id  = t.show_id
ORDER BY t.show_id;
