Example Usage:

```
./make_icon.py -i italian_flag_1.jpeg --text '[
    {"text":"B1","x":550,"y":520,"font":"/System/Library/Fonts/Helvetica.ttc","font_size":440,"color":"#052D12","anchor":"mm","weight":"9","angle":20},
    {"text":"ITALIANO","x":530,"y":730,"font":"/System/Library/Fonts/Supplemental/Arial Bold.ttf","font_size":95,"color":"black","anchor":"mm","weight":"3"}
 ]'
```

Set `font` independently in each JSON object. It accepts `.ttf`, `.otf`, and
`.ttc` font file paths.

Set `angle` to rotate a text item clockwise by that many degrees. For example,
`"angle":20` rotates the text 20 degrees clockwise; `-20` rotates it
counterclockwise.

Or use the Makefile with comma-separated fields in this order:
`text,x,y,font,font_size,color,anchor,weight,angle`. Leave a field empty to use
its default value. Run it without text specs to render the input image as icons
with no text:

```
make start
make start "Italian A1",695,320,,50,white,,5
make start B1,550,520,,440,#052D12,,9,20 francais,530,730,,440,#052D12,,3
```

The Makefile automatically uses the first file it finds named `input_flag.jpeg`,
`input_flag.jpg`, or `input_flag.png`. If the source image is not 1024x1024,
the script scales and center-crops it to a 1024x1024 icon. Override the input
when needed:

```
make start INPUT=another-image.jpeg B1,550,520,,440,#052D12,,9,20
```

---

## Last Usages
### Italian
- A1:
```
make start A1,720,130,,250,#E1D3C6,,3,0
```

- A2:
```
make start A2,715,130,,250,#E1D3C6,,3,0
```

- B1:
```
make start B1,715,130,,250,#E1D3C6,,3,0
```


- B2:
```
make start B2,710,130,,250,#E1D3C6,,3,0
```

- C1:
```
make start C1,715,130,,250,#E1D3C6,,3,0
```


means:
text = Italian A1
x = 695
y = 320
font = default
font_size = 50
color = white
anchor = default
weight = 5
angle = 20

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
make start A1,765,805,,160,white,,3
```

- A2:
```
make start A2,765,805,,160,white,,3
```


- B1:
```
make start B1,780,806,,160,white,,3
```


- B2:
```
make start B2,780,806,,160,white,,3
```

- C1:
```
make start C1,775,806,,160,white,,3
```
