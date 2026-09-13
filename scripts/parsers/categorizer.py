"""Keyword-based merchant → spending category classifier."""

# Each rule: (list of lowercase substrings, category)
# Rules are checked in order; first match wins.
RULES = [
    # Income — checked first so salary deposits aren't miscategorised
    (['accenture', 'kindergeld', 'bundesagentur', 'elterngeld', 'kinderzuschlag'], 'Income'),
    # Salary duplicate label
    (['gehalt', 'lohn'], 'Salary'),
    # Rent
    (['bilstein', 'miete', 'hausverwaltung', 'wohnungsbau', 'vermieter'], 'Rent'),
    # Childcare — specific only; 'bad vilbel'/'kreis'/'stadt bad' removed (too broad)
    (['kindergarten', 'kita ', 'kinderbetreuung', 'trauminsel',
      'jugendamt', 'wetteraukreis', 'essensgeld kinder', 'spielgeld kinder'], 'Childcare'),
    # Groceries
    (['herkules', ' aldi', 'aldi ', 'lidl', 'penny ', 'rewe', 'edeka', 'netto ',
      'kaufland', 'spiceland', 'baris markt', 'bereket', 'asia markt', 'tegut',
      'globus', 'real ', 'hit ', 'denns', 'basic bio', 'denn',
      'jamoona', 'go asia', 'anusch', 'zam zam', 'kahouach',
      'jaffna basar', 'orient city markt', 'orient master', 'yasmin markt',
      'nahkauf', 'norma ', 'despar', 'spar tigne', 'todis supermercato',
      'carrefour', 'crf exp', 'frischemarkt', 'eataly',
      'hasan kayatuz',          # local Turkish butcher/grocer Bad Vilbel
      'toprak',                 # Turkish grocery Frankfurt
      'mh muller handels',      # local market Bad Vilbel
      ], 'Groceries'),
    # Dining
    (['kfc', 'maydonoz', 'kaiyo', 'mcdonald', 'kentucky fried',
      'bäcker', 'backerei', 'baecker', 'backwerk', 'backhaus', 'backstation',
      'hinnerbacker', 'hinnerbaecker', 'allianz gastro', 'brezel',
      'elas grill', 'allianz one', 'super 8', 'butcher kebap', 'juice box',
      'dunkin', 'five guys', 'indien food', 'schloss-orangerie', 'schloss orangerie',
      'thi mong', 'ditsch', 'yormas',
      'gastro',                 # catches Consortium Gastronomie, S U Gastro etc.
      'ristorante', 'trattoria', 'caffetteria', 'cafeteria',
      'autogrill', 'eiscafe', 'piramide',
      'pizza hut', 'amrest',    # AmRest = KFC/PH/BK franchise operator
      'quickers', 'taandoori',
      'galeria markthalle', 'galeria bedankt',
      'myzeil',                 # Foods MyZeil food court
      'palmo',                  # PalmoFriedChicken
      'palmen grill',
      'bombay lounge', 'bombay',
      'ran maruay',             # Thai
      'best worscht',           # Frankfurt specialty
      'stullen factory',        # sandwiches Frankfurt
      'babba baguette',
      'curry club',
      'kanne cafe', 'kanne - kh',  # Kanne cafe (incl. KH Nordwest hospital branch)
      'babo di pane',           # bread/bakery Frankfurt
      'westgrill',
      'indian pepper', 'mr phung',
      'crobag',                 # Le Crobag bakery chain
      'food galay', 'food factory', 'food market',
      'veggie love', 'china box',
      'venchi',                 # Italian gelato/chocolate
      'sapores',                # Sapores Saigon Streetfood
      'mamas fast food',        # fast food Frankfurt
      'wiener cafehaus',        # cafe
      'tiffany s kiosk',        # Malta kiosk/snacks
      'cafe kissler',
      'nazar gmbh',             # Frankfurt restaurant
      # Malta dining
      'vecchia napoli', 'sphinx pastizz', 'southern fried', 'mama knows',
      'chapeau/', 'la brioscia', 'daves/', 'dave.s/', 'relish/departure',
      'ta gorg',
      # Italy dining
      'al gazebo', 'miscele e fuoco', 'cococ food', 'fratelli di pizza',
      'al canton', 'quanto basta', 'tre scalini', 'rinaldini',
      'khirul miah', 'itinere', 'buffet roma', 'ssp italy',
      'imperiale/', 'la bella pollastrella', 'bar murano',
      'amici snc', 'il golosone', 'alba veneta',
      'ayasofia', 'rovereto turkish kebap', 'miah liton',
      'bistro', 'restaurant', 'pizzeria', 'döner', 'kebab',
      'burger', 'subway', 'starbucks', 'vapiano', 'nordsee',
      'gaststätte', 'imbiss', 'snack', 'sushi', 'saravana'], 'Dining'),
    # Utilities
    (['stadtwerke', 'vodafone', 'ard zdf', 'ard/zdf', 'dradio', 'beitragsservice',
      'deutsche post', 'telekom', 'o2 ', ' o2', '1&1', 'ewe ', 'innogy',
      'e.on', 'mainova', 'lidl connect', 'congstar'], 'Utilities'),
    # Transport
    (['deutsche bahn', 'db bahn', 'db ', ' db ', 'rmv', 'mvv', 'hvv', 'bvg',
      'parkhaus', 'parking', 'tankstelle', 'shell', 'aral', 'esso', 'total ',
      'bp ', 'jet ', 'sixt', 'europcar', 'hertz', 'flughafen', 'airport',
      'ryanair', 'easyjet', 'lufthansa', 'eurowings', 'condor', 'check24 flug',
      'malta public', 'mopla',
      'vgf ', 'transdev',       # Frankfurt & regional public transport
      'taxi ',                  # catches Taxi Schumann, Taxi Gaida, SumUp .Taxi…
      'gozo channel',           # Malta ferry
      'fiumicino',              # Rome airport
      'vela spa', 'ferrovia',   # Venice water/rail transport
      'tegelbergbahn',          # Bavaria cable car
      'rovereto m1', 'duomo cordusio', 'lima m1',  # Milan metro
      'supremetravel', 'supreme travel',  # Malta travel agency
      'malta sightseeing',      # Malta tour bus
      'termini b dir', 'termini dir. lau',  # Rome Termini bus routes
      'roma ostiense ss',       # Rome Ostiense bus/rail
      ], 'Transport'),
    # Healthcare
    (['apotheke', 'apothe', 'farmacia',  # German + Italian pharmacies
      'pharmacy', 'doktor', 'dr.', 'krankenhaus', 'klinik',
      'optik', 'güldener', 'fielmann', 'sanikonzept', 'zahnarzt', 'physio',
      'sanitätshaus', 'kinderarztprax',
      'aäa gmbh',               # medical practice Bad Vilbel
      ], 'Healthcare'),
    # Insurance
    (['versicherung', 'allianz', 'huk', 'axa', 'signal iduna', 'ergo',
      'generali', 'debeka', 'barmer', 'tk ', 'techniker'], 'Insurance'),
    # Entertainment
    (['netflix', 'spotify', 'apple.com', 'google play', 'steam', 'playstation',
      'disney', 'prime video', 'dazn', 'sky ', 'joyn', 'tvnow', 'kino',
      'theater', 'museum', 'concert', 'ticket', 'eventim',
      'zoo frankfurt', 'tiergarten',   # Frankfurt & Nuremberg zoos
      'aquarium',                       # Malta National Aquarium
      ], 'Entertainment'),
    # Shopping (catch-all for retail after specifics above)
    (['amazon', 'rossmann', 'dm-', 'dm ', ' dm ', 'woolworth', 'h&m', 'h+m',
      'zara', 'primark', 'c&a', 'saturn', 'mediamarkt', 'ikea', 'obi ',
      'bauhaus', 'hornbach', 'deichmann', 'humanic', 'snipes', 'tedi', 'new yorker',
      'nkd ',                   # NKD discount clothing
      'poco einricht',          # POCO furniture
      ' kik', 'kik ',           # KiK discount clothing
      'tkmaxx',                 # TK Maxx
      'shoe4you',               # shoe store
      'rofu kinder',            # toy store
      'decathlon',              # sports store
      'douglas', 'parfuemerie', # Douglas perfumery
      'kathe wohlfahrt',        # Christmas decorations
      'puma outlet',            # PUMA outlet store
      'lovisa',                 # jewellery
      'bialetti',               # Italian kitchenware
      'muller gmbh co',         # Müller drugstore
      'exchange edicola',       # souvenir shop
      'paypal', 'klarna',
      'booking.com', 'check24 hotel', 'hotel', 'airbnb'], 'Shopping'),
    # Banking / ATM
    (['sparkasse', 'volksbank', 'commerzbank', 'deutsche bank', 'ing ',
      'dkb ', 'n26', 'geldautomat', 'atm', 'schufa', 'american express',
      'postbank', 'comdirect', 'siehe anlage',
      'wise europe',            # Wise international transfer
      'stadtkasse',             # city tax payments
      ], 'Banking'),
]


def categorize(merchant: str, tx_type: str = '') -> str:
    m = merchant.lower()
    t = tx_type.lower()

    for keywords, category in RULES:
        if any(k in m for k in keywords):
            return category

    # Type-based fallbacks
    if any(x in t for x in ['geldautomat', 'auszahlung geldauto', 'atm']):
        return 'Banking'
    if 'gutschrift' in t:
        return 'Income'

    return 'Other'
