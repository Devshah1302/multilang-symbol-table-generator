"""
samples.py - Built-in sample programs for every language.

Each language has a correct program and a program with errors, so the
analyzer can be demonstrated without typing any code.
"""

SAMPLES = {
    "C": {
        "Valid program - marks report": r"""#include <stdio.h>
#define MAX 5

int add(int a, int b) {
    return a + b;
}

int main() {
    int marks[MAX] = {90, 85, 70, 60, 95};
    int total = 0;
    float average;
    char grade = 'A';
    for (int i = 0; i < MAX; i++) {
        total = add(total, marks[i]);
    }
    average = total / 5.0;
    printf("Total = %d, Average = %.2f, Grade = %c\n", total, average, grade);
    return 0;
}
""",
        "Program with errors": r"""#include <stdio.h>
#define PI 3.14

int main() {
    int count = 10;
    int count = 20;
    float price = 99.5;
    int qty = "five";
    int rounded = price;
    char letter;
    int age;
    total = count + 5;
    PI = 3.5;
    scanf("%d", age);
    printf("%c %d\n", letter, rounded)
    return 0;
}
""",
    },
    "C++": {
        "Valid program - class and object": r"""#include <iostream>
#include <string>
using namespace std;

class Student {
public:
    string name;
    int marks;

    Student(string n, int m) {
        name = n;
        marks = m;
    }

    char grade() {
        if (marks >= 90) return 'A';
        return 'B';
    }
};

int main() {
    const double BONUS = 2.5;
    Student s1("Dev", 88);
    double finalMarks = s1.marks + BONUS;
    cout << s1.name << " got " << finalMarks << " grade " << s1.grade() << endl;
    return 0;
}
""",
        "Program with errors": r"""#include <iostream>
#include <string>
using namespace std;

class Account {
public:
    string owner;
    double balance;

    void deposit(double amount) {
        balance = balance + amount;
    }
};

int main() {
    const int LIMIT = 1000;
    Account acc;
    string id = 101;
    int points = 4.75;
    LIMIT = 2000;
    acc.deposit(500);
    cout << acc.balance << total << endl;
    int x = 5;
    if (x = 10) {
        cout << "ten" << endl;
    }
    return 0;
}
""",
    },
    "Java": {
        "Valid program - shopping cart": r"""import java.util.ArrayList;

public class Main {
    static final double TAX_RATE = 0.18;

    static double priceWithTax(double price) {
        return price + price * TAX_RATE;
    }

    public static void main(String[] args) {
        ArrayList<String> items = new ArrayList<>();
        items.add("Pen");
        items.add("Book");
        int count = items.size();
        double total = 0;
        for (String item : items) {
            total = total + priceWithTax(50);
            System.out.println(item);
        }
        String message = "Items: " + count;
        boolean expensive = total > 100;
        System.out.println(message + ", expensive = " + expensive);
    }
}
""",
        "Program with errors": r"""public class Main {
    public static void main(String[] args) {
        final int MAX_USERS = 50;
        int score = 9.5;
        float ratio = 2.5;
        String name = 25;
        boolean active = 1;
        int level;
        int score = 10;
        MAX_USERS = 60;
        System.out.println(level);
        System.out.println(bonus);
        String a = "hi";
        String b = "hi";
        if (a == b) {
            System.out.println(name + ratio + active)
        }
    }
}
""",
    },
    "Python": {
        "Valid program - student results": r"""import math

PASS_MARK = 40

class Student:
    def __init__(self, name, marks):
        self.name = name
        self.marks = marks

    def average(self):
        return sum(self.marks) / len(self.marks)


def result(student):
    avg = student.average()
    status = "Pass" if avg >= PASS_MARK else "Fail"
    return f"{student.name}: {math.floor(avg)} ({status})"


students = [Student("Dev", [80, 75, 90]), Student("Tirth", [35, 30, 45])]
for s in students:
    print(result(s))
""",
        "Program with errors": r"""import os

age = 21
name = "Dev"
message = "Age: " + age
total = price * 2
score = 50
score = "fifty"

def greet(person):
    greeting = "Hello"
    return "Hi " + person

print(greet(name))
print(undefined_function())
print(10 / 0)
""",
        "Syntax error": r"""def add(a, b)
    return a + b
""",
    },
    "JavaScript": {
        "Valid program - shopping bill": r"""const TAX = 0.18;
let cart = [120, 80, 45];

function total(prices) {
    let sum = 0;
    for (const p of prices) {
        sum += p;
    }
    return sum;
}

const withTax = (amount) => amount + amount * TAX;

class Customer {
    constructor(name) {
        this.name = name;
    }
    greet() {
        return `Hello ${this.name}`;
    }
}

const buyer = new Customer("Dev");
const bill = withTax(total(cart));
console.log(buyer.greet(), bill.toFixed(2));
""",
        "Program with errors": r"""const PI = 3.14;
let score = 50;
let score = 60;
PI = 3.1416;
const LIMIT;
console.log(count);
let count = 5;
if (score == "50") {
    console.log("equal");
}
result = score * 2;
console.log(average);
let unused = 10;
""",
    },
}
