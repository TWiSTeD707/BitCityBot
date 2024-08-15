import requests


def get_crypto_rate(crypto: str = 'bitcoin', currency: str = 'rub') -> float:
    url = f'https://api.coingecko.com/api/v3/simple/price?ids={crypto}&vs_currencies={currency}'
    response = requests.get(url)
    data = response.json()
    return data[crypto][currency]