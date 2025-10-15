export type MustVisitDetail = {
  identifier: string;
  name: string;
  city: string;
  intro: string;
  description: string[];
  seasons: string[];
};

const splitDescription = (text: string): string[] =>
  text.split(/\n\s*\n/).map((paragraph) => paragraph.trim()).filter(Boolean);

const formatSeasons = (seasons: string[]): string[] =>
  seasons.map((s) => s.slice(0, 1).toUpperCase() + s.slice(1));

export const MUST_VISIT_DETAILS: Record<string, MustVisitDetail> = {
  gornergrat: {
    identifier: "1dfb3334-4bca-49f7-9e97-e7094e6c8df8",
    name: "Gornergrat",
    city: "Zermatt",
    intro:
      "Surrounded by 29 towering peaks, including the iconic Matterhorn, Gornergrat is the panoramic podium of the Pennine Alps.",
    description: splitDescription(
      "Adventure world \nIn summer, marvel at the reflection of the Matterhorn on the surface of the Riffelsee and enjoy great hiking trails and cycling routes on this adventure mountain. In winter, the beautiful tobogganing run from Rotenboden to Riffelberg is just one of the experiences on offer, with sunny pistes, a children’s ski park and snowball fights on the winter hiking trail all sure to delight both young and old.\n\nINFORMATION\nAltitude: 3,089 m a.s.l. Arrival: Train from Brig/Visp to Zermatt, from Zermatt by cog railway to the Gornergrat. Timetable: Operates year-round, during the high season in 24-minute intervals. Travel duration to summit: 33 minutes to the top, 44 minutes back.\nAttractions: View on 29 peaks above 4,000 m a.s.l., the glaciers of Monte Rosa, reflection of Matterhorn in Lake Riffel, journey with the Gornergrat cog railway to 3,089 m a.s.l.. Food & beverage: Restaurant with a view onto Monte Rosa mountain massif, self-service restaurant, gourmet ticket.\nSpecials: ZOOOM the Matterhorn – a multimedia experience on the Gornergrat.\n\nReduced rate mountain rail ascent with the Swiss Travel Pass/GA travelcard.\n\nDownload comprehensive information, including highlights and an adventure map: PDF Info Guide.\n\nPurchase your Gornergrat mountain railway ticket online.\n\nMOUNTAIN DAY TRIPS\nBuy your mountain rail ascent return tickets now.\n\nTimetable and tickets."
    ),
    seasons: formatSeasons(["summer", "winter", "spring", "autumn"]),
  },
  muerrenbahn: {
    identifier: "14586645-e603-4e15-8b22-0bc88389cd06",
    name: "Mürrenbahn",
    city: "Interlaken",
    intro:
      "Ride the historic aerial cableway and adhesion railway from Lauterbrunnen into the car-free village of Mürren high above the Lauterbrunnen Valley.",
    description: splitDescription(
      "From Lauterbrunnen to Grütschalp \nSince 2006, visitors have been able to ascend the first 685 meters of the Grütschalp (1481 meters) by aerial cable car. The cable car can accommodate 100 persons on each ride. At the same time it can carry 6,000 kilograms of freight. The ride takes 4 minutes. \n\nFrom Grütschalp to Mürren \nAn adhesion railway runs on the romantic stretch across alpine meadows to Mürren. This ride traverses an additional 147 meters. \n\nMürren is not accessible by car. For this reason freight transport is especially important. Transportation is carried out by means of containers, which are transferred to the freight compartment of the adhesion train at the intermediate station’s ultra-modern loading facility. \n\nThe Lauterbrunnen-Mürren mountain train was opened in 1891. There is an additional means of traveling to Mürren: by aerial cable car from Stechelberg (the aerial cable car continues onward via Gimmelwald to Schilthorn)."
    ),
    seasons: formatSeasons(["spring", "summer", "autumn", "winter"]),
  },
  faelensee: {
    identifier: "79b6d511-3336-4ec8-8d35-d316825500a9",
    name: "Lake Fälen",
    city: "Appenzell",
    intro:
      "This dramatic alpine lake, tucked between sheer rock walls of the Alpstein range, mirrors the sky and peaks like a Swiss fjord.",
    description: splitDescription(
      "There are often remnants of snow even in high summer, while gentian and alpine anemones flower in the areas with Southern exposure. A hiking trail runs along the northern shore of the lake, fishermen try their luck here and in the dog days of summer, there is even an intrepid bather or two that brave the chilly waters, at best 18° C. There is a lovely inn, the Bollenwie, a much-visited destination for hikers, mountaineers, and fishermen. Not only is the view phenomenal, but also the Rösti which makes the 2-hour-hike all the more worthwhile.\n\nHow to get there:\nBy public transportation (train or postbus) or car from St. Gallen/Appenzell to Brülisau. From Brülisau there is a hiking trail leading to Lake Fälen, the hike takes 1 3/4 hours."
    ),
    seasons: formatSeasons(["summer", "spring", "autumn"]),
  },
  stoos: {
    identifier: "d10151a7-c9ae-48f5-8227-0f985b87ea62",
    name: "Stoosbahn",
    city: "Schwyz",
    intro:
      "Glide to the traffic-free village of Stoos on the world’s steepest funicular, a feat of Swiss engineering that tilts cabins to keep riders level.",
    description: splitDescription(
      "The technical marvel will delight guests of all ages: the Stoosbahn reaches a gradient of 110% (47 degrees). It is the steepest funicular railway in the world. What’s really fascinating is that the spherical cabins adapt to the gradient perfectly. This enables passengers to stay upright at all times.\n\nThe journey from Schwyz to Stoos takes between 4 and 7 minutes. In the process, the Stoosbahn covers a total ascent of around 744 metres, and travels over two bridges and through three tunnels. After 1,740 metres, the funicular reaches the upper station in the middle of the mountain village. A natural paradise awaits with a wide range of leisure activities.\n\nThe holiday village of Stoos, sitting at about 1,300 metres up, can be found nestled in the Alpine landscape of Central Switzerland. There is a wide range of leisure activities on offer: from a hike along the ridge trail with impressive plunging views to fun in the water at the Little Stoos Lake or a leisurely picnic. Here, everyone will find the experience to suit them. In winter, ski slopes, winter hiking trails and snowshoe trails delight guests.\n\nGetting there: From Schwyz train station, buses take about 20 minutes to reach the “Stoosbahn” bus stop. Alternatively, take the car from Schwyz in the direction of Muotathal. The valley station and large car park is located directly on the road.\n\nINFORMATION\nGradient 110% (47.73 degrees) Altitude difference 744 metres Length 1,740 metres Duration Between 4 and 7 minutes Timetable Runs all year round. Special comments Fully included in the Swiss Travel Pass (Flex) / GA Travelcard.\nBook your tickets."
    ),
    seasons: formatSeasons(["summer", "winter", "spring", "autumn"]),
  },
  "grosser-mythen": {
    identifier: "6343af66-3e67-4f05-be3e-23b7a1f4b80f",
    name: "Photo Spot Grosser Mythen",
    city: "Schwyz",
    intro:
      "Climb the 47 hairpin bends to Grosser Mythen for a 360° panorama over the lakes and peaks that cradle the birthplace of Switzerland.",
    description: splitDescription(
      "Address:\nRickenbachstrasse 163\n6432 Rickenbach\n\nParking: \nCable car parking, metered\n\nFootpath: \nCable car (subject to charge), approx. 20 min. \nChange required at Fiescheralp station, \nfootpath from mountain station 1 min."
    ),
    seasons: formatSeasons(["summer", "autumn", "spring"]),
  },
  "mount-rigi": {
    identifier: "synthetic-mount-rigi",
    name: "Mount Rigi",
    city: "Lucerne",
    intro:
      "Known as the Queen of the Mountains, Mount Rigi couples vintage cogwheel rides with spa stops and sweeping lake-and-Alp views.",
    description: splitDescription(
      "Accessible by historic cogwheel railway from Vitznau or Arth-Goldau and panoramic cable car from Weggis, Mount Rigi delivers 360-degree vistas across Lake Lucerne, Lake Zug and the Bernese Alps. Visitors combine sunrise trips, spa stops at Rigi Kaltbad and leisurely ridge hikes, making it a quintessential Lucerne excursion year-round."
    ),
    seasons: formatSeasons(["summer", "spring", "autumn", "winter"]),
  },
  "interlaken-water-sports": {
    identifier: "ae303d42-839c-4955-8124-df0e37f4bdd7",
    name: "Interlaken Water Sports",
    city: "Interlaken",
    intro:
      "Kayak mirror-flat lakes, raft glacier-fed rivers, or try canyoning thrills—Interlaken is Switzerland’s aquatic adventure playground.",
    description: splitDescription(
      "Whether an intoxicating kayak tour on the glassy surface of Lake Brienz or a ride on the waves of a wild mountain stream; the region around Interlaken offers water sports enthusiasts a large choice. During guided tours, which do not require any prior knowledge, hikers get to enjoy the breathtaking nature or search for the next adrenaline rush.\n\nThese are the activities on offer: \n\n• SUP \n• kayaking \n• canoeing \n• canyoning \n• river rafting \n• boat hire \n• wakesurfing \n• water skiing \n• wakeboarding \n• pedaloing\n\nMore information."
    ),
    seasons: formatSeasons(["summer", "spring", "autumn"]),
  },
  gurten: {
    identifier: "7840a02c-91c4-4fe7-85e3-7132312dc527",
    name: "Gurten",
    city: "Bern",
    intro:
      "Bern’s local mountain pairs funicular ease with festival vibes, open-air lawns, and sweeping Alpine-and-Aare vistas.",
    description: splitDescription(
      "Traffic-free Gurten is reached on a ride in the red carriages of the funicular railway, departing from Waben, in just a few minutes. And impressive views over and around the Aare and city of Berne, as well as Mittelland and Jura as far as the Alps are viewed from the observation tower up here. \n\nSince 1899, the Gurtenbahn funicular railway has climbed the 858m mountain where day-trippers relax and enjoy the view. Used as a golf course until 1959, the Gurten fields now offer free access and plenty of barbecue spots. Families appreciate the electric cars, miniature railway with steam locomotives and cog-wheel sections, climbing frame, frisbee and bowling. \n\nIn winter – given the right snow conditions – there is a toboggan run to the Grünenboden middle station and a miniature ski lift on the Gurten fields. INFORMATION\nAltitude: 856m \nAccessibility: From Bahnhof Bern by S-Bahn to Wabern or with Tram No. 9 to Wabern-Gurtenbahn, funicular railway to Gurten \nView: Over the city of Berne, and from the viewing tower, all-round views of the Alps, Emmen Valley and Jura – and from the Ostsignal information center, across the Bernese Alps with Eiger, Mönch and Jungfrau \nAttractions: Miniature railway, in part with steam locomotives and cog-wheel sections, large playing field (former Gurten golfing green) \nCulinary aspects: «Tapis Rouge» self-service restaurant, Restaurant «Gurtners» with stylish interior, Brunch at the Gurten Pavilion \nOvernight stays: only a few hotel rooms \nGroups: Gewölbekeller, banquet facilities, up-town stage hall (between 80 and several hundred people) \nWinter: Mountain rail in operation, toboggan-run by sufficient snow \nSpecial comments: Annual Gurten Festival\nReduced rate mountain rail ascent with the Swiss Travel Pass/GA travelcard."
    ),
    seasons: formatSeasons(["summer", "spring", "autumn", "winter"]),
  },
  "old-city-of-bern": {
    identifier: "09a45cf8-2676-489a-a0a3-e0cb4f4b5dbd",
    name: "Old City of Bern",
    city: "Bern",
    intro:
      "Arcaded streets, Renaissance fountains, and river bends make Bern’s UNESCO-listed old town a time capsule framed by Alpine views.",
    description: splitDescription(
      "UNESCO World Cultural Heritage Site \nThe capital of Switzerland has many charms. Its quaint old town is framed by the Aare River and offers spectacular views of the Alps.\n\nWith its 6 km of limestone buildings and medieval arcades, its Renaissance fountains with colorful figures, and its beautiful cathedral surrounded by picturesque rooftops, Bern, founded in 1191, is truly a gem of medieval architecture in Europe."
    ),
    seasons: formatSeasons(["spring", "summer", "autumn", "winter"]),
  },
};

export const getMustVisitDetail = (slug: string) => MUST_VISIT_DETAILS[slug];
