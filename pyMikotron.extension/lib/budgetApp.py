import math as m

class Category:
    
    def __init__(self,name):
        self.name = name
        self.ledger = []#list of transactions

    def __str__(self):
        title = f'{self.name:*^30}\n'
        items = ''
        total = 0
        for i in self.ledger:
            am = float(i['amount'])
            total += am
            desc = i['description']
            items += f'{desc[0:23]:23}' + f'{am:>7.2f}' + '\n'
        output = title + items + 'Total: ' + str(total)
        return output

    def deposit (self, amount, desc=""):
        x = {'amount':amount, 'description':desc}
        self.ledger.append(x)

    def withdraw (self, amount, desc=""):
        if self.check_funds(amount):
            am = -(amount)
            x = {'amount':am, 'description':desc}
            self.ledger.append(x)
            print(f'Withdrawn {amount} from {self.name}')
            return True
        else:
            print(f'Insufficient funds in {self.name}')
            return False

    def get_balance(self):
        balance = 0
        for i in self.ledger:
            _am = float(i['amount'])
            balance += _am
        return balance

    def transfer(self, amount, cat):
        funds = self.check_funds(amount)
        if funds:
            cat.deposit(amount, f'Transfer from {self.name}')
            self.withdraw(amount, f'Transfer to {cat.name}')
            print(f'Tansferred {amount} from {self.name} to {cat.name}')
            return True
        else:
            print(f'Insufficient funds in {self.name}')
            return False

    def check_funds(self, amount): #use it for widtraw and transfer
        balance = self.get_balance()
        if balance < amount:
            return False
        else:
            return True

def create_spend_chart(categories):
    withdrawals = []
    total_withdrawn = 0
    percentages_withdrawn = []
    out = 'Percentage spent by category'
    for c in categories:
        total_withdraw = 0
        for i in c.ledger:
            if i['amount'] < 0:
                total_withdraw += abs(i['amount'])
        withdrawals.append([c.name,total_withdraw])
        total_withdrawn += total_withdraw
    
    for n,v in withdrawals:
        percentages_withdrawn.append((n, m.floor((v/total_withdrawn)*100)))

    _rango = range(100,-1,-10)
    for r in _rango:
        start = f'{r:>3}|'
        for n,p in percentages_withdrawn:
            if p >= r:
                start += ' o '
            else:
                start += '   '
        out += '\n' + start + ' '
    
    out += '\n    '+"---"*(len(categories))+'-'
    _letter = [c.name for c in categories]
    for i in range(max(len(name) for name in _letter)):
        line = '     '
        for name in _letter:
            if i < len(name):
                line += name[i]+"  "
            else:
                line += '   '
        out += '\n' + line
    print(out)
    return out

food = Category('Food')
food.deposit(1000, 'initial deposit')
food.withdraw(10.15, 'groceries')
food.withdraw(15.89, 'restaurant and more food for dessert')
clothing = Category('Clothing')
food.transfer(50, clothing)
clothing.withdraw(10.15, 'socks')
food.deposit(1000)
print(food)
create_spend_chart([clothing,food, clothing])

"""Your create_spend_chart function builds the vertical name rows but the lines are not padded to a uniform length and the required two spaces between each category (and after the final category) are missing. Adjust the loop that assembles the name lines so it adds two spaces after each ch...
"""