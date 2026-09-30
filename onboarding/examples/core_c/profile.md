## accounts.csv.gz (5,000 rows; 3,000 sampled)
- accountId: number, id; e.g. 51784857, 51124192
- custId: ; e.g. C-1131166, C-1526809
- accountType: word, code; e.g. CHK, SVG
- balanceAmt: money, number; e.g. 7277.83, 6475.50
- openedDate: date [YYYY/MM/DD]; e.g. 2013/08/20, 2020/09/05
- statusCode: number, code; e.g. 1, 1
## customers.csv.gz (3,000 rows; 3,000 sampled)
- custId: id; e.g. C-2060066, C-1467788
- givenName: word; e.g. Teresa, Amber
- familyName: word; e.g. Briggs, Wheeler
- birthDate: date [YYYY/MM/DD]; e.g. 1994/06/07, 1990/02/27
- taxRef: tax_token, id; e.g. 3101-0D8D-B4A7-FAE0, 26E8-D03E-9581-57CE
- addressLine: street, id; e.g. 2656 Spring LANE, 2698 Park DRIVE
- cityName: word, code; e.g. Linden Crossing, Wrenfield
- stateCode: state, word, code; e.g. PA, PA
- postalCode: number, zip5; e.g. 15401, 15318
- mobile: phone; e.g. +1 724 555 7945, +1 412 555 5589
- createdTs: epoch_seconds, number, phone; e.g. 1380067200, 1280448000
## postings.csv.gz (55,938 rows; 3,000 sampled)
- postingId: number, id; e.g. 900639956, 900267871
- accountId: number; e.g. 50941332, 51365070
- postedTs: epoch_seconds, number, phone, id; e.g. 1781477997, 1776176210
- amt: money, number; e.g. -14.70, -306.18
- typeCode: word, code; e.g. POS, EFTOUT
- channel: word, code; e.g. web, app
