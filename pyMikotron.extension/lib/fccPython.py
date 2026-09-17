""" order = list(range(1,5))
langs = ['Python', 'C++', 'Java', 'English']
for i in order:
    collection = list(zip(order, langs))
print(collection)

catalog = []
anims = ['Dog', 'Cat', 'Bird', 'Fish']
for index, animal in enumerate(anims):
    catalog.append(f"{index}: {animal}")
    print(f"{index}: {animal}")
print(catalog)

developers = ['Naomi', 'Dario', 'Jessica', 'Tom']
ids = [1, 2, 3, 4]
for name, id in zip(developers, ids):
    print(f'Name: {name}')
    print(f'ID: {id}')

print(catalog[1])

nums = [1, 2, 3, 4, 5]
result = [(num,'even') if num%2==0 else (num, 'odd') for num in nums]
print(result)

words = ['tree', 'sky', 'mountain', 'river', 'cloud', 'sun']
def is_long_word(word):
    return len(word) > 4
long_words = list(filter(is_long_word, words))
print(long_words) # ['mountain', 'river', 'cloud']

celsius = [0, 10, 20, 30, 40]
def to_fahrenheit(temp):
    return (temp * 9/5) + 32
fahrenheit = list(map(to_fahrenheit, celsius))
print(fahrenheit) # [32.0, 50.0, 68.0, 86.0, 104.0]

numbers = [1, 2, 3, 4, 5]
even_numbers = list(filter(lambda x: x % 2 == 0, numbers))
print(even_numbers)  # [2, 4]

pizza = dict([('name', 'Margherita Pizza'), ('price', 8.9), ('calories_per_slice', 250), ('toppings', ['mozzarella', 'basil'])])
print(pizza["name"])
print(pizza.get("price"))
print(pizza.keys())
print(pizza.values())
print(pizza.items())
print(pizza.pop("calories_per_slice"))
print(pizza.items( ))
pizza.update({'price': 9.5, 'calories_per_slice': 300})
print(pizza.items())
print(list(enumerate(pizza)))
print(list(enumerate(pizza.items())))
[print(pizz) for pizz in pizza.items()]"""