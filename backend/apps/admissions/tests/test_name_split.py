from django.test import SimpleTestCase

from apps.admissions.tenancy import split_full_name


class SplitFullNameTests(SimpleTestCase):
    def check(self, full_name, first, last):
        self.assertEqual(split_full_name(full_name), (first, last), full_name)

    def test_surname_first_is_swapped(self):
        self.check('Muzaffarova Manzura', 'Manzura', 'Muzaffarova')
        self.check('Saydazimova Sofiya', 'Sofiya', 'Saydazimova')
        self.check('Ne’matillayev Oyatillo', 'Oyatillo', 'Ne’matillayev')
        self.check("Ne'matillayev Oyatillo", 'Oyatillo', "Ne'matillayev")
        self.check('Abdukarimov Muhsinbek', 'Muhsinbek', 'Abdukarimov')
        self.check('Karimbekova Dilnoza', 'Dilnoza', 'Karimbekova')
        self.check('Ahmadzoda Farrux', 'Farrux', 'Ahmadzoda')
        self.check('MUZAFFAROVA Manzura', 'Manzura', 'MUZAFFAROVA')

    def test_given_name_first_keeps_the_order(self):
        self.check('Sofiya Saydazimova', 'Sofiya', 'Saydazimova')
        self.check('Akbar Axmedov', 'Akbar', 'Axmedov')
        self.check('Ali Valiyev', 'Ali', 'Valiyev')

    def test_two_surname_looking_words_keep_the_order(self):
        self.check('Eva Ivanova', 'Eva', 'Ivanova')
        self.check('Abdullayev Karimov', 'Abdullayev', 'Karimov')

    def test_neither_looks_like_a_surname_keeps_the_order(self):
        self.check('Dilnoza Rustam', 'Dilnoza', 'Rustam')

    def test_single_word_and_empty(self):
        self.check('Muzaffarova', 'Muzaffarova', '')
        self.check('Sofiya', 'Sofiya', '')
        self.check('', '', '')
        self.check('   ', '', '')

    def test_cyrillic(self):
        self.check('Музаффарова Манзура', 'Манзура', 'Музаффарова')
        self.check('Иванов Пётр', 'Пётр', 'Иванов')
        self.check('Манзура Музаффарова', 'Манзура', 'Музаффарова')
        self.check('Пётр Иванов', 'Пётр', 'Иванов')
        self.check('Достоевская Анна', 'Анна', 'Достоевская')
        self.check('Ева Иванова', 'Ева', 'Иванова')

    def test_russian_style_endings(self):
        self.check('Kovalskaya Anna', 'Anna', 'Kovalskaya')
        self.check('Nowitskiy Pavel', 'Pavel', 'Nowitskiy')

    def test_patronymic_stays_with_the_last_name(self):
        self.check("Ali Valiyev Bahodir o'g'li", 'Ali', "Valiyev Bahodir o'g'li")
        self.check('Muzaffarova Manzura Bahodir qizi', 'Manzura', 'Muzaffarova Bahodir qizi')
        self.check('Sardor Karimov Ravshan o‘g‘li', 'Sardor', 'Karimov Ravshan o‘g‘li')
        # A patronymic marker alone is not split off.
        self.check('Bahodir qizi', 'Bahodir', 'qizi')

    def test_middle_words_follow_the_same_rule(self):
        self.check('Karimova Dilnoza Rustamovna', 'Dilnoza Rustamovna', 'Karimova')
        self.check('Sardor Ali Karimov', 'Sardor', 'Ali Karimov')
