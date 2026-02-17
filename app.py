from flask import Flask, render_template, request
import pandas as pd
from collections import deque

app = Flask(__name__)

# ===============================
# LOAD DATASETS
# ===============================
ingredients_df = pd.read_csv("data/ingredients.csv")
recipes_df = pd.read_csv("data/recipes.csv")
recipe_ingredients_df = pd.read_csv("data/recipe_ingredients.csv")
recipe_instructions_df = pd.read_csv("data/recipe_instructions.csv")

# Ingredient list for checkbox display
ingredient_options = ingredients_df.to_dict(orient="records")


# ===============================
# BUILD GRAPH (BASED ON SHARED INGREDIENTS)
# ===============================
def build_graph():
    graph = {rid: set() for rid in recipes_df["recipe_id"]}

    grouped = recipe_ingredients_df.groupby("recipe_id")["ingredient_id"].apply(set)

    for r1 in grouped.index:
        for r2 in grouped.index:
            if r1 != r2 and grouped[r1].intersection(grouped[r2]):
                graph[r1].add(r2)

    return graph


recipe_graph = build_graph()

# ===============================
# BFS RECOMMENDATION
# ===============================
def bfs_recommendations(
    start_nodes,
    calorie_min, calorie_max,
    fat_min, fat_max,
    carb_min, carb_max,
    protein_min, protein_max
):
    visited = set()
    queue = deque(start_nodes)
    results = []

    while queue:
        rid = queue.popleft()

        if rid in visited:
            continue
        visited.add(rid)

        recipe = recipes_df[recipes_df["recipe_id"] == rid].iloc[0]

        if (
            calorie_min <= recipe["calories"] <= calorie_max and
            fat_min <= recipe["fat"] <= fat_max and
            carb_min <= recipe["carbohydrates"] <= carb_max and
            protein_min <= recipe["protein"] <= protein_max
        ):
            results.append(recipe)

        print(f"Calorie range: {calorie_min} - {calorie_max}")
        print(f"Sample recipe calories: {recipes_df['calories'].head(5).tolist()}")

        for neighbor in recipe_graph.get(rid, []):
            if neighbor not in visited:
                queue.append(neighbor)

    return results

def score_recipe(recipe_id, selected_ingredients):
    recipe_ings = set(
        recipe_ingredients_df[
            recipe_ingredients_df["recipe_id"] == recipe_id
        ]["ingredient_id"]
    )
    return len(recipe_ings.intersection(selected_ingredients))


# ===============================
# ROUTES
# ===============================
@app.route("/")
def index():
    return render_template("user_form.html", ingredient_options=ingredient_options)


@app.route("/get_recommendation", methods=["POST"])
def get_recommendation():

    # -------- USER INPUT --------
    age = int(request.form["age"])
    height_ft = float(request.form["height"])
    weight = float(request.form["weight"])
    gender = request.form["gender"]
    activity = request.form["activity"]
    goal = request.form["goal"]

    # -------- VALIDATION --------
    if not (5 <= age <= 100):
        return render_template("error.html", message="Age must be between 5 and 100")

    if not (3 <= height_ft <= 8):
        return render_template("error.html", message="Height must be between 3 and 8 feet")

    if not (20 <= weight <= 200):
        return render_template("error.html", message="Weight must be between 20 and 200 kg")

    # -------- BMI & BMR --------
    # -------- BMI & BMR --------
    height_cm = height_ft * 30.48
    bmi = round(weight / ((height_cm / 100) ** 2), 2)

    if gender == "male":
        bmr = (10 * weight) + (6.25 * height_cm) - (5 * age) + 5
    else:
        bmr = (10 * weight) + (6.25 * height_cm) - (5 * age) - 161

    activity_map = {"low": 1.2, "moderate": 1.55, "high": 1.725}
    daily_calories = bmr * activity_map.get(activity, 1.2)

    # NEW: Assume recipes are for one meal (1/3 of daily calories)
    meal_calories = daily_calories / 3

    if goal == "weight_loss":
        calorie_min = meal_calories - 300
        calorie_max = meal_calories
    elif goal == "weight_gain":
        calorie_min = meal_calories
        calorie_max = meal_calories + 300
    else:
        calorie_min = meal_calories - 200
        calorie_max = meal_calories + 200

    calorie_min = max(50, calorie_min)
    calorie_max = min(1000, calorie_max)

    # -------- INGREDIENT SELECTION --------
    selected_ingredients = list(map(int, request.form.getlist("ingredient_id")))

    if not selected_ingredients:
        return render_template("no_match.html")

    # recipe_match_counts = (
    #     recipe_ingredients_df
    #     .query("ingredient_id in @selected_ingredients")
    #     .groupby("recipe_id")
    #     .size()
    # )
    recipe_match_counts = (
        recipe_ingredients_df
        [recipe_ingredients_df["ingredient_id"].isin(selected_ingredients)]
        .groupby("recipe_id")
        .size()
    )

    start_nodes = recipe_match_counts.index.tolist()
    if not start_nodes:
        start_nodes = recipes_df["recipe_id"].tolist()

    # if not start_nodes:
    #     return render_template("no_match.html")

    # -------- NUTRITION LIMITS --------
    fat_min, fat_max = 0, 40
    carb_min, carb_max = 0, 100
    protein_min, protein_max = 0, 60


    recommendations = bfs_recommendations(
        start_nodes,
        calorie_min, calorie_max,
        fat_min, fat_max,
        carb_min, carb_max,
        protein_min, protein_max
    )

    if not recommendations:
        recommendations = bfs_recommendations(
            start_nodes,
            calorie_min - 200, calorie_max + 200,
            fat_min, fat_max,
            carb_min, carb_max,
            protein_min, protein_max
        )

    # Final fallback
    if not recommendations:
        recommendations = recipes_df[
            recipes_df["recipe_id"].isin(start_nodes)
        ].to_dict(orient="records")

# STILL empty? show no_match safely
    if not recommendations:
        return render_template("no_match.html")

    recommendations = sorted(
        recommendations,
        key=lambda r: score_recipe(r["recipe_id"], selected_ingredients),
        reverse=True
    )

    best_recipe = recommendations[0]

    recipe_id = best_recipe["recipe_id"]

    # -------- FETCH INGREDIENT NAMES --------
    recipe_ing_ids = recipe_ingredients_df[
        recipe_ingredients_df["recipe_id"] == recipe_id
    ]["ingredient_id"]

    recipe_ingredients = ingredients_df[
        ingredients_df["ingredient_id"].isin(recipe_ing_ids)
    ]["ingredient_name"].tolist()

    # -------- FETCH INSTRUCTIONS --------
    instructions_df = recipe_instructions_df[
        recipe_instructions_df["recipe_id"] == recipe_id
    ].sort_values(["method", "step_no"])

    instructions_1 = instructions_df[
        instructions_df["method"] == "method_1"
    ]["instruction"].tolist()

    instructions_2 = instructions_df[
        instructions_df["method"] == "method_2"
    ]["instruction"].tolist()

    return render_template(
        "recipe.html",
        recipe=best_recipe,
        ingredients=recipe_ingredients,
        instructions_1=instructions_1,
        instructions_2=instructions_2,
        bmi=bmi
    )

if __name__ == "__main__":
    app.run(debug=True)
