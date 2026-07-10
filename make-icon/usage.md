Example Usage:

```
./make_icon.py -i italian_flag_1.jpeg --text '[
    {"text":"B1","x":550,"y":520,"font":"/System/Library/Fonts/Helvetica.ttc","font_size":440,"color":"#052D12","anchor":"mm","weight":"9"},
    {"text":"ITALIANO","x":530,"y":730,"font":"/System/Library/Fonts/Supplemental/Arial Bold.ttf","font_size":95,"color":"black","anchor":"mm","weight":"3"}
 ]'
```

Set `font` independently in each JSON object. It accepts `.ttf`, `.otf`, and
`.ttc` font file paths.

Or use the Makefile with comma-separated fields in this order:
`text,x,y,font,font_size,color,anchor,weight`. Leave a field empty to use its
default value:

```
make start B1,550,520,,440,#052D12,,9 francais,530,730,,440,#052D12,,3
```

The Makefile automatically uses the first file it finds named `input_flag.jpeg`,
`input_flag.jpg`, or `input_flag.png`. Override it when needed:

```
make start INPUT=another-image.jpeg B1,550,520,,440,#052D12,,9
```

---

## Last Usages
### French
- A1:
```
make start A1,695,320,,300,#021A3D,,5 fr,180,560,,220,white,,3 ançais,330,560,,220,#021A3D,,3
```

- A2:
```
make start A2,620,320,,300,#021A3D,,5 fr,195,560,,220,white,,3 ançais,340,560,,220,#021A3D,,3
```

- B1:
```
make start B1,660,320,,300,#021A3D,,5 fr,195,560,,220,white,,3 ançais,340,560,,220,#021A3D,,3
```

---

### Swedish
- A1:
```
make start svenska,756,820,,70,white,,2 A1,756,900,,110,white,,3
```

- A2:
```
make start svenska,240,400,,210,white,,3 A2,440,610,,450,white,,5
```