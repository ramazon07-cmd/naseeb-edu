"""Fixed exchange rates for official aid amounts.

Universities publish aid in their own currency. The match compares it with the student's budget in USD, so
``import_official_aid`` converts with this table. The rates are approximate USD per one unit of the currency,
fixed on the date below and changed only by editing this file (no live lookup, so a re-import is repeatable).
ARS and VES are left out on purpose (too volatile for a fixed rate), and "unknown" is not a currency. A currency that is not listed is not converted: its USD fields stay empty (unknown), never guessed.
"""
from decimal import Decimal

RATES_AS_OF = '2026-11-23'
USD_PER_UNIT = {
    'USD': Decimal('1'),
    'EUR': Decimal('1.08'),
    'GBP': Decimal('1.27'),
    'CAD': Decimal('0.73'),
    'AUD': Decimal('0.65'),
    'NZD': Decimal('0.60'),
    'CHF': Decimal('1.13'),
    'SEK': Decimal('0.095'),
    'NOK': Decimal('0.093'),
    'DKK': Decimal('0.145'),
    'PLN': Decimal('0.25'),
    'CZK': Decimal('0.043'),
    'HUF': Decimal('0.0027'),
    'TRY': Decimal('0.029'),
    'AED': Decimal('0.272'),
    'SAR': Decimal('0.267'),
    'QAR': Decimal('0.275'),
    'KWD': Decimal('3.25'),
    'JPY': Decimal('0.0065'),
    'KRW': Decimal('0.00072'),
    'CNY': Decimal('0.138'),
    'RMB': Decimal('0.138'),
    'HKD': Decimal('0.128'),
    'TWD': Decimal('0.031'),
    'SGD': Decimal('0.75'),
    'MYR': Decimal('0.22'),
    'THB': Decimal('0.029'),
    'IDR': Decimal('0.000062'),
    'PHP': Decimal('0.017'),
    'VND': Decimal('0.00004'),
    'INR': Decimal('0.012'),
    'ZAR': Decimal('0.055'),
    'KZT': Decimal('0.0020'),
    'RUB': Decimal('0.011'),
    'BRL': Decimal('0.18'),
    'MXN': Decimal('0.052'),
    'ILS': Decimal('0.27'),
    'EGP': Decimal('0.02'),
    'AZN': Decimal('0.59'),
    'GEL': Decimal('0.37'),
    'RON': Decimal('0.22'),
    'BGN': Decimal('0.55'),
    'ISK': Decimal('0.0073'),
    'COP': Decimal('0.00025'),
    'MOP': Decimal('0.125'),
    'OMR': Decimal('2.60'),
    'BND': Decimal('0.75'),
    'PEN': Decimal('0.27'),
    'JOD': Decimal('1.41'),
    'CRC': Decimal('0.002'),
    'CLP': Decimal('0.00105'),
    'PKR': Decimal('0.0036'),
    'LBP': Decimal('0.0000112'),
    'UYU': Decimal('0.025'),
    'BHD': Decimal('2.65'),
    'TND': Decimal('0.32'),
    'BDT': Decimal('0.0082'),
    'UAH': Decimal('0.024'),
    'IQD': Decimal('0.00076'),
    'GHS': Decimal('0.075'),
    'KGS': Decimal('0.0116'),
    'GTQ': Decimal('0.13'),
    'PYG': Decimal('0.000128'),
    'SDG': Decimal('0.00166'),
    'NGN': Decimal('0.00065'),
    'LKR': Decimal('0.0033'),
    'DOP': Decimal('0.0165'),
    'HNL': Decimal('0.039'),
    'PAB': Decimal('1'),
    'BAM': Decimal('0.55'),
}


def rate(currency):
    """USD per one unit of ``currency``, or None when the currency is not in the table."""
    return USD_PER_UNIT.get((currency or '').strip().upper())


def to_usd(amount, currency):
    """``amount`` in ``currency`` as whole USD, or None when either is missing or the currency is unlisted."""
    factor = rate(currency)
    if amount is None or factor is None:
        return None
    return int((Decimal(amount) * factor).quantize(Decimal('1')))
