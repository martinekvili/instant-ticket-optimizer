from typing import Final, AnyStr, TypedDict, Tuple

import bs4
import requests
from bs4 import BeautifulSoup
import json
import re
import pandas


total_count_regex: Final[re.Pattern[AnyStr]] = re.compile(r"(\d+,?\d*)\smillió")
count_regex: Final[re.Pattern[AnyStr]] = re.compile(r"([\d|\s]+)(?:\sdb)?")
win_amount_regex: Final[re.Pattern[AnyStr]] = re.compile(r"([\d|\s]+)(?:\sFt)?")


class InstantTicket(TypedDict):
    urlkey: str
    winning_dsc: str
    expected_value: float
    win_chance: float


def parse_tickets(page: BeautifulSoup) -> list[InstantTicket] | None:
    container = page.find('div', class_="instant-ticket__container instant-ticket__container--header")
    init_script = container['ng-init']
    if not init_script.startswith('itCtrl.init(') or not init_script.endswith(', false);'):
        return None

    return json.loads(init_script[12:-9])


def find_remove_script(page: BeautifulSoup) -> str | None:
    parent_container = page.find('div', class_="main-container")
    for script in parent_container.find_all('script', type='text/javascript'):
        script_str = str(script.string)
        if 'var sorsjegyek = [];' in script_str:
            return script_str

    return None


def parse_excluded_tickets(page: BeautifulSoup) -> list[str]:
    remove_script = find_remove_script(page)
    if remove_script is None:
        return []

    exluded_regex = r"document\.querySelector\('\.instant-ticket__grid \.instant-ticket__grid__item:not" \
                    r"\(\.instant-ticket__grid__item--promo\) \.instant-ticket__box > a\[href=\"/sorsjegyek/(.*?)\"]'\)"
    return re.findall(exluded_regex, remove_script)


def download_tickets() -> list[InstantTicket] | None:
    html = requests.get('https://bet.szerencsejatek.hu/sorsjegyek')
    page = BeautifulSoup(html.text, 'html.parser')

    tickets = parse_tickets(page)
    if tickets is None:
        return None

    excluded_tickets = parse_excluded_tickets(page)
    return [ticket for ticket in tickets if ticket['urlkey'] not in excluded_tickets]


def get_total_count(win_description: BeautifulSoup) -> float:
    header_text = win_description.find('th', colspan="2").get_text()
    total_count_text = re.search(total_count_regex, header_text).group(1)

    return float(total_count_text.replace(",", ".")) * 1000000


def parse_number_value(cell: bs4.Tag, regex: re.Pattern[AnyStr]) -> int | None:
    text = re.search(regex, cell.get_text(strip=True))
    if text is None:
        return None

    return int(re.sub(r"\s", "", text.group(1)))


def determine_expected_value_and_win_chance(ticket: InstantTicket) -> Tuple[float, float]:
    win_description = BeautifulSoup(ticket['winning_dsc'], 'html.parser')
    total_count = get_total_count(win_description)

    winning_count = 0
    total_win_amount = 0.0

    row: bs4.Tag
    for row in win_description.find_all('tr'):
        cells: list[bs4.Tag] = row.find_all('td')
        if len(cells) != 2:
            continue

        count = parse_number_value(cells[0], count_regex)
        if count is None:
            continue

        win_amount = parse_number_value(cells[1], win_amount_regex)
        if win_amount is None:
            continue

        winning_count += count
        total_win_amount += count * win_amount

    return total_win_amount / total_count, winning_count / total_count


def main() -> None:
    tickets = download_tickets()
    if tickets is None:
        exit(1)

    for ticket in tickets:
        expected_value, win_chance = determine_expected_value_and_win_chance(ticket)
        ticket['expected_value'] = expected_value
        ticket['win_chance'] = win_chance

    df = pandas.DataFrame.from_records(tickets, columns=['name', 'price', 'expected_value', 'win_chance'])
    df['roi'] = df['expected_value'] / df['price'].astype(int)

    df.sort_values(['roi', 'win_chance'], ascending=False, inplace=True)
    print(df)


if __name__ == '__main__':
    main()
