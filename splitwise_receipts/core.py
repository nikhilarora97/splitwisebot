"""Receipt parsing and exact, deterministic cent allocation."""
import re
from decimal import Decimal, InvalidOperation


def cents(value):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d != d.quantize(Decimal('.01')) or abs(d) > 1000000:
            raise ValueError()
        return int(d * 100)
    except (InvalidOperation, ValueError):
        raise ValueError('Use amounts with at most two decimal places, below 1,000,000.')


def money(n):
    return f'{Decimal(n) / 100:.2f}'


def allocate(total, weights):
    if not weights or sum(weights) <= 0 or any(w < 0 for w in weights):
        raise ValueError('Choose at least one person for every item.')
    sign = -1 if total < 0 else 1
    total = abs(total)
    denominator = sum(weights)
    parts = [total * w // denominator for w in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % denominator), i))
    for i in order[:total - sum(parts)]:
        parts[i] += 1
    return [sign * n for n in parts]


def calculate(draft):
    people = draft['people']
    ids = [int(p['id']) for p in people]
    if not ids or len(ids) != len(set(ids)) or any(i <= 0 for i in ids):
        raise ValueError('Select unique Splitwise members.')
    if int(draft['payer_id']) not in ids:
        raise ValueError('The payer must be one of the selected people.')
    if not draft.get('description', '').strip():
        raise ValueError('Add an expense description.')
    items = draft['items']
    if not items:
        raise ValueError('Add at least one receipt item.')
    bases = [0] * len(ids)
    subtotal = 0
    for item in items:
        amount = cents(item['amount'])
        assigned = [int(i) for i in item['people']]
        if not assigned or len(assigned) != len(set(assigned)) or set(assigned) - set(ids):
            raise ValueError('Assign each item to selected people, without duplicates.')
        shares = allocate(amount, [int(i in assigned) for i in ids])
        bases = [a + b for a, b in zip(bases, shares)]
        subtotal += amount
    tax, tip, discount = [cents(draft.get(k, '0')) for k in ('tax', 'tip', 'discount')]
    if min(tax, tip, discount) < 0 or min(bases) < 0 or subtotal <= 0:
        raise ValueError('Item shares must be nonnegative; subtotal must be positive. Enter discounts as positive amounts.')
    total = subtotal + tax + tip - discount
    if total <= 0 or discount > subtotal:
        raise ValueError('Discount cannot exceed subtotal, and total must be positive.')
    # Allocate discount first, then tax and tip against each person’s original item share.
    owed = bases[:]
    for adjustment in (-discount, tax, tip):
        owed = [a + b for a, b in zip(owed, allocate(adjustment, bases))]
    expected = draft.get('receipt_total', '').strip()
    if expected and cents(expected) != total:
        raise ValueError(f'Receipt total is {expected}, but items + tax + tip − discount = {money(total)}. Correct the receipt before posting.')
    if any(n < 0 for n in owed):
        raise ValueError('Discount creates a negative share. Adjust the item amounts.')
    return {'total': money(total), 'subtotal': money(subtotal), 'shares': [dict(id=p['id'], name=p['name'], owed=money(n), paid=money(total if int(p['id']) == int(draft['payer_id']) else 0)) for p, n in zip(people, owed)]}


def parse_text(text):
    result = dict(description='Receipt', currency='USD', items=[], tax='0.00', tip='0.00', discount='0.00', receipt_total='', warnings=['Check every amount against the receipt. Local scanning does not interpret split instructions.'])
    lines = [s.strip() for s in text.splitlines() if s.strip()]
    if lines:
        result['description'] = lines[0][:120]
    for line in lines:
        match = re.match(r'^(.*?)\s*\$?(-?\d[\d,]*\.\d{2})\s*$', line)
        if not match:
            continue
        label, amount = match.groups()
        amount = amount.replace(',', '')
        key = label.strip().lower()
        if any(t in key for t in ('subtotal', 'sub total', 'cash', 'change', 'visa', 'mastercard', 'balance', 'tender', 'saving')):
            continue
        if 'total' in key:
            result['receipt_total'] = amount
        elif 'tax' in key:
            result['tax'] = money(cents(result['tax']) + cents(amount))
        elif any(t in key for t in ('tip', 'gratuity', 'service charge')):
            result['tip'] = money(cents(result['tip']) + cents(amount))
        elif any(t in key for t in ('discount', 'coupon')):
            result['discount'] = money(cents(result['discount']) + abs(cents(amount)))
        elif label.strip():
            result['items'].append(dict(name=label.strip(), amount=amount, people=[]))
    if not result['items']:
        result['warnings'].append('No line items recognized. Enter items manually or use the AI reader.')
    return result
