#!/usr/bin/env python3
#
# This file is part of MachtSinn
#
# Copyright (C) 2019 Michael Schönitzer and contributors
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
from typing import List, Tuple

import mysql.connector
import requests

from dbconf import (
    db_host,
    db_name,
    db_passwd,
    db_table_lang_codes,
    db_table_lexemes,
    db_table_main,
    db_table_texts,
    db_user,
)


# Run a query against a web-api
def runquery(url, params={}, session=requests):
    headers = {"User-Agent": user_agent}
    r = session.get(url, headers=headers, params=params)
    if r.status_code == 200:
        return r.json()["results"]
    return None


# Run a Spaql-Query
def runSPARQLquery(query):
    return runquery(endpoint_url, params={"format": "json", "query": query})["bindings"]


endpoint_url = "https://query.wikidata.org/sparql"

user_agent = "makesense 0.0.2 by User:MichaelSchoenitzer"

# This variable should be incremented every time the query is changed
# and the database should be pruned from data that is not in the query anymore
dataversion = 2

with open("query.sparql") as f:
    sparql = f.read()

try:
    mydb = mysql.connector.connect(
        host=db_host,
        user=db_user,
        passwd=db_passwd,
        database=db_name,
        charset="utf8",
        use_unicode=True,
    )
except:
    mydb = mysql.connector.connect(host=db_host, user=db_user, passwd=db_passwd)

    mycursor = mydb.cursor()
    mycursor.execute("CREATE DATABASE {}".format(db_name))
    mydb = mysql.connector.connect(
        host=db_host,
        user=db_user,
        passwd=db_passwd,
        database=db_name,
        charset="utf8",
        use_unicode=True,
    )


mycursor = mydb.cursor()

mycursor.execute(
    """CREATE TABLE IF NOT EXISTS `{}` (
     `lang` INT,
     `QID` INT,
     `LID` INT,
     `Status` INT,
     `version` INT,
     PRIMARY KEY (`lang`,`QID`,`LID`)
);""".format(
        db_table_main
    )
)

mycursor.execute(
    """CREATE TABLE IF NOT EXISTS `{}` (
     `LID` INT,
     `category` INT,
     `genus` INT,
     `version` INT,
     PRIMARY KEY (`LID`)
);""".format(
        db_table_lexemes
    )
)

mycursor.execute(
    """CREATE TABLE IF NOT EXISTS `{}` (
     `lang` INT,
     `QID` INT,
     `lemma` TEXT CHARACTER SET utf8 NOT NULL,
     `gloss` TEXT CHARACTER SET utf8 NOT NULL,
     `version` INT,
     PRIMARY KEY (`lang`,`QID`)
);""".format(
        db_table_texts
    )
)

print("Running Query…")
res = runSPARQLquery(sparql)

print("Collection results…")
sql = """INSERT INTO {0}
         (lang, QID, LID, Status, version)
         VALUES
         (%s, %s, %s, %s, {1})
         ON DUPLICATE KEY UPDATE version = {1}""".format(
    db_table_main, dataversion
)
values = []
text_sql = """INSERT INTO {0}
         (lang, QID, lemma, gloss, version)
         VALUES
         (%s, %s, %s, %s, {1})
         ON DUPLICATE KEY UPDATE version = {1}""".format(
    db_table_texts, dataversion
)
text_values = []
lexeme_sql = """INSERT INTO {0}
         (lid, category, genus, version)
         VALUES
         (%s, %s, %s, {1})
         ON DUPLICATE KEY UPDATE version = {1}""".format(
    db_table_lexemes, dataversion
)
lexeme_values = []
for row in res:
    lang = int(row["lang"]["value"][32:])
    lid = int(row["lexeme"]["value"][32:])
    qid = int(row["item"]["value"][32:])

    lemma = row["lemma"]["value"]
    desc = row["desc"]["value"]

    cat = int(row["cat"]["value"][32:])
    try:
        genus = int(row["genus"]["value"][32:])
    except KeyError:
        genus = None

    values.append((lang, qid, lid, 0))
    text_values.append((lang, qid, lemma, desc))
    lexeme_values.append((lid, cat, genus))

print(
    "Adding {} rows to Database…".format(
        len(values) + len(text_values) + len(lexeme_values)
    )
)

try:
    mycursor.executemany(sql, values)
    mycursor.executemany(text_sql, text_values)
    mycursor.executemany(lexeme_sql, lexeme_values)
except:
    print("Problem executing:")
    print(mycursor.statement)

mydb.commit()

exit(0)

# Query for the wikimedia language codes
with open("querylangcodes.sparql") as f:
    sparql = f.read()

res = runSPARQLquery(sparql)
langlist = [(row["lang"]["value"][32:], row["code"]["value"]) for row in res]


mycursor.execute(
    """CREATE TABLE IF NOT EXISTS `{}` (
     `lang` INT,
     `code` TEXT,
     PRIMARY KEY (`lang`)
);""".format(
        db_table_lang_codes
    )
)
sql = "INSERT IGNORE INTO {} (lang, code) VALUES (%s, %s)".format(db_table_lang_codes)
mycursor.executemany(sql, langlist)
mydb.commit()


# Delete old entries
mycursor.execute(
    """DELETE FROM {} WHERE version < {} and status = 0""".format(
        db_table_main, dataversion
    )
)
