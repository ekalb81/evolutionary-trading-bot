import json
import random
import uuid
import copy
import os

def load_data(gen_0_dir):
    results_path = os.path.join(gen_0_dir, 'results.json')
    population_path = os.path.join(gen_0_dir, 'population.json')
    
    with open(results_path, 'r') as f:
        results_data = json.load(f)
        
    with open(population_path, 'r') as f:
        population_data = json.load(f)
        
    pop_dict = {strat['id']: strat for strat in population_data}
    return results_data.get('results', []), pop_dict

def tournament_selection(participants_pool, k=3):
    participants = random.sample(participants_pool, k)
    fittest = max(participants, key=lambda x: x.get('fitness', -9999))
    return fittest['strategy_id']

def blend_crossover(s1, s2):
    child_dict = {}
    for k in s1:
        if k in s2 and type(s1[k]) in (int, float) and type(s1[k]) is not bool:
            v1 = s1[k]
            v2 = s2[k]
            avg = (v1 + v2) / 2.0
            offset = avg * random.uniform(-0.05, 0.05)
            new_val = avg + offset
            if type(v1) is int:
                child_dict[k] = max(1, int(round(new_val)))
            else:
                child_dict[k] = round(new_val, 4)
        else:
            child_dict[k] = copy.deepcopy(s1[k])
    return child_dict

def crossover(p1, p2):
    child = {}
    
    # 1. Single-point crossover for structural sections
    sections = ['indicators', 'entry_rule', 'exit_rule']
    pt = random.randint(1, len(sections) - 1)
    
    for i, sec in enumerate(sections):
        if i < pt:
            child[sec] = copy.deepcopy(p1[sec])
        else:
            child[sec] = copy.deepcopy(p2[sec])
            
    # 2. Blend crossover for parameter sections
    child['risk_management'] = blend_crossover(p1.get('risk_management', {}), p2.get('risk_management', {}))
    child['position_sizing'] = blend_crossover(p1.get('position_sizing', {}), p2.get('position_sizing', {}))
    
    # 3. Attributes
    child['archetype'] = p1.get('archetype', 'mixed')
    child['seeding_type'] = 'crossover'
    
    return child

def mutate_rule_comparator(rule):
    if not isinstance(rule, dict):
        return
        
    if 'comparator' in rule:
        comp = rule['comparator']
        standard_comps = ['>', '<', '>=', '<=', '==', '!=']
        cross_comps = ['crosses_above', 'crosses_below']
        
        if comp in standard_comps:
            rule['comparator'] = random.choice([c for c in standard_comps if c != comp])
        elif comp in cross_comps:
            rule['comparator'] = 'crosses_above' if comp == 'crosses_below' else 'crosses_below'
            
    if 'left' in rule: 
        mutate_rule_comparator(rule['left'])
    if 'right' in rule: 
        mutate_rule_comparator(rule['right'])

def mutate_genome(child):
    # Numeric mutation: tweak indicator periods ±5%
    for ind in child.get('indicators', []):
        if 'params' in ind and 'period' in ind['params']:
            p = ind['params']['period']
            new_p = int(p * random.uniform(0.95, 1.05))
            if new_p == p: # Force a tweak if rounding caused no change
                new_p += random.choice([-1, 1])
            ind['params']['period'] = max(2, new_p)
            
    # Numeric mutation: risk params
    if 'risk_management' in child:
        for k in ['stop_loss_pct', 'take_profit_pct']:
            if k in child['risk_management']:
                val = child['risk_management'][k]
                child['risk_management'][k] = round(val * random.uniform(0.95, 1.05), 4)

    # Structural mutations setup
    structural_choices = ['change_comparator', 'add_indicator', 'remove_indicator']
    choice = random.choice(structural_choices)
    
    if choice == 'change_comparator':
        if random.random() < 0.5 and 'entry_rule' in child:
            mutate_rule_comparator(child['entry_rule'])
        elif 'exit_rule' in child:
            mutate_rule_comparator(child['exit_rule'])
            
    elif choice == 'add_indicator':
        # Add a basic indicator. We use ind_X where X is the next index available.
        inds = child.get('indicators', [])
        next_id = f"ind_{len(inds)}"
        # Simple random indicator
        new_ind = {
            "id": next_id,
            "type": random.choice(["SMA", "EMA", "RSI"]),
            "params": {"period": random.randint(10, 50)},
            "value_type": "series"
        }
        inds.append(new_ind)
        child['indicators'] = inds

    elif choice == 'remove_indicator':
        inds = child.get('indicators', [])
        # Only remove if we have more than 2 indicators to avoid breaking minimum requirements
        if len(inds) > 2:
            inds.pop()
            child['indicators'] = inds


def main():
    GEN_0_DIR = 'data/evolution/gen_000'
    GEN_1_DIR = 'data/evolution/gen_001'
    os.makedirs(GEN_1_DIR, exist_ok=True)
    
    results, pop_dict = load_data(GEN_0_DIR)
    
    # Sort results by fitness (descending)
    results.sort(key=lambda x: x.get('fitness', -9999), reverse=True)
    
    POPULATION_SIZE = 200
    ELITISM_COUNT = 5
    MUTATION_RATE = 0.1
    
    new_population = []
    
    # 1. Elitism: Top 5 strategies passed unchanged
    for i in range(min(ELITISM_COUNT, len(results))):
        strat_id = results[i]['strategy_id']
        elite = copy.deepcopy(pop_dict[strat_id])
        
        # Fresh identity for Gen 1
        elite['id'] = str(uuid.uuid4())
        elite['generation'] = 1
        elite['parent_id'] = strat_id # Optional traceability
        new_population.append(elite)
        
    # Pool for tournament selection (top 50%)
    top_half_count = POPULATION_SIZE // 2
    top_half_results = results[:top_half_count]
    
    # 2. Selection, Crossover & Mutation
    while len(new_population) < POPULATION_SIZE:
        p1_id = tournament_selection(top_half_results, k=3)
        p2_id = tournament_selection(top_half_results, k=3)
        
        # Try to avoid self-breeding
        retries = 0
        while p1_id == p2_id and retries < 5:
            p2_id = tournament_selection(top_half_results, k=3)
            retries += 1
            
        p1 = pop_dict[p1_id]
        p2 = pop_dict[p2_id]
        
        # Perform Crossover
        child = crossover(p1, p2)
        
        # 3. Perform Mutation
        if random.random() < MUTATION_RATE:
            mutate_genome(child)
            
        child['id'] = str(uuid.uuid4())
        child['generation'] = 1
        child['name'] = f"GEN1_{child['id'][:8]}"
        child['parent1_id'] = p1_id
        child['parent2_id'] = p2_id
        
        new_population.append(child)
        
    # 4. Save Output
    out_file = os.path.join(GEN_1_DIR, 'population.json')
    with open(out_file, 'w') as f:
        json.dump(new_population, f, indent=2)
        
    print(f"Generation 1 breeder completed.")
    print(f"Population generated: {len(new_population)}")
    print(f"Output saved to: {out_file}")

if __name__ == '__main__':
    main()
