#!/usr/bin/env python3

import argparse
from pathlib import Path
import yaml

META_KEYS = ["name", "czk", "percent", "leftovers"]

def main():
    parser = argparse.ArgumentParser(prog="yamplan",
                                description="Finance planner driven by YAML")
    parser.add_argument("plan", help="Plan to upon which to operate")
    args = parser.parse_args()

    filepath = Path(args.plan)
    plan = read_file(filepath)
    income = plan["income"]["czk"]
    calculate(plan["expenses"], income, [])
    stats = {}


def read_file(filepath):
    with open(filepath, 'r') as input_file:
        content = input_file.read()
    try:
        yaml.safe_load(content)
    except yaml.scanner.ScannerError as exc:
        print(exc)
    else:
        return yaml.safe_load(content)

def get_dict_at_path(full_dict, path):
    for item in path:
        full_dict = full_dict[item]
    return full_dict

def calculate(full_plan, plan, budget, path):
    plan_ro = plan.copy()
    path_copy = path.copy()
    plan = get_dict_at_path(plan, path)
    print(plan)
    # parent = path[-1]
    current_category = None
    for key in META_KEYS:
        if key in plan_ro.items():
            match key:
                case "czk":
                    print("Calculate percentage")
                case "percent":
                    print("Calculate CZK")
                case "name":
                    pass
                case "leftovers":
                    pass
    for key, value in plan_ro.items():
        if key not in META_KEYS:
            current_category = key
            path_copy.append(current_category)
            calculate(plan, budget, path_copy)




# def calculate(expenses, parent, parent_name):
#     if type(parent) is int:
#         print("This is the top-level!")
#         expenses["czk"] = parent
#         parent = expenses
#     for key, value in expenses.items():
#         print(key)
#         whatevs = ["expanses", "wants", "donations"]
#         var = copydict
#         for item in whatevs:
#             var = var[item]
#         copydict[whatevs]
#         match key:
#             case "percent":
#                 budget = parent["czk"] // 100 * value
#                 print(f"Budget for {parent_name}: {budget}")
#                 parent[parent_name]["czk"] = budget
#             case "czk":
#                 print("Will calculate the percentage")
#             case "name":
#                 pass
#             case _:
#                 calculate(value, expenses, key)
