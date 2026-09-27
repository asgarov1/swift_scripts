# Translate json files
```
make start ../../Swedish/swedish-a2/swedish-a2 en
make start ../../Portuguese/portuguese-a2/portuguese-a2 en
```

# Translate AppConfig (can NOT be done at the same time as the previous command - have to execute one at a time)
```
make translate-appconfig ../../Swedish/swedish-a2/swedish-a2 english
make translate-appconfig ../../Portuguese/portuguese-a2/portuguese-a2 english
```

# Translate one English phrase
```
make translate good morning
make translate good morning TARGET_LANG=italian
make translate good morning TARGET_LANG=portuguese
make translate good morning TARGET_LANG=pt
```
