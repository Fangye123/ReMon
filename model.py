from docplex.mp.model import Model
import numpy as np

#switches = 24
switches = 28
flows = 10
rates = 3

# path = [
#     [0, 5, 10, 18],
#     [1, 5, 10, 14, 19],
#     [2, 3, 6, 8, 11, 15, 20],
#     [3, 6, 8, 11, 15, 21, 22],
#     [4, 7, 9, 13, 17, 23],
#     [0, 5, 8, 11, 15, 16, 22, 23],
#     [1, 5, 8, 11, 15, 21, 22],
#     [2, 3, 6, 8, 10, 18],
#     [3, 6, 8, 11, 15, 20],
#     [4, 3, 6, 8, 11, 15, 14, 19]
# ]
path = [
    [18, 27, 19, 2, 6, 7, 4, 5, 8],
    [20, 23, 24, 25, 1, 13, 12, 11, 10],
    [21, 20, 23, 24, 25, 1, 13, 12, 15, 16, 17],
    [22, 21, 20, 23, 24, 25, 1, 13, 12, 15, 16],
    [23, 24, 25, 1, 13, 12, 15, 16, 9],
    [18, 27, 19, 2, 6, 3, 0, 1, 13, 12, 11, 10],
    [20, 23, 24, 25, 1, 0, 4, 6, 7, 4, 5, 8],
    [21, 20, 23, 24, 25, 1, 13, 12, 15, 16, 9],
    [22, 18, 27, 19, 2, 6, 7, 4, 5, 8, 9, 16],
    [23, 24, 25, 1, 13, 12, 15, 16, 17]
]

d = [5000, 5000, 20000, 5000, 5000, 5000, 20000, 20000, 5000, 5000]
capacity = []
for s in range(switches):
    capacity.append(100)

accuracy = [[[0 for r in range(rates)] for f in range(flows)] for s in range(switches)]
for s in range(switches):
    for f in range(flows):
        if s in path[f]:
            if path[f].index(s) == len(path[f]):
                accuracy[s][f][0] = 100
                accuracy[s][f][1] = 98
                accuracy[s][f][2] = 95
            else:
                accuracy[s][f][0] = 95
                accuracy[s][f][1] = 93
                accuracy[s][f][2] = 90

RC = [[[0 for r in range(rates)] for f in range(flows)] for s in range(switches)]
for s in range(switches):
    for f in range(flows):
        if s in path[f]:
            RC[s][f][0] = d[f] / 100
            RC[s][f][1] = d[f] / 500
            RC[s][f][2] = d[f] / 1000
        else:
            RC[s][f][0] = 100000
            RC[s][f][1] = 100000
            RC[s][f][2] = 100000

m = Model('assignment_problem')

#decision variables
x = m.binary_var_dict((s, f, r) for s in range(switches) for f in range(flows) for r in range(rates))

#objective function
total_cost = m.sum(0.2*accuracy[s][f][r]*x[s, f, r]-0.8*RC[s][f][r]*x[s, f, r] for s in range(switches) for f in range(flows) for r in range(rates))
m.maximize(total_cost)

#constraints
for f in range(flows):
    m.add_constraint(m.sum(x[s, f, r] for s in range(switches) for r in range(rates)) >= 1)
for s in range(switches):
    m.add_constraint(m.sum(RC[s][f][r]*x[s, f, r] for f in range(flows) for r in range(rates)) <= capacity[s])
for f in range(flows):
    m.add_constraint(m.sum(x[s, f, r] for s in path[f] for r in range(rates)) >= 0)

solution = m.solve(log_output=True)
m.print_information()


a = solution.get_all_values()
result = [[[0 for r in range(rates)] for f in range(flows)] for s in range(switches)]
count = 0
total_accuracy = 0
total_cost = 0
for s in range(switches):
    for f in range(flows):
        for r in range(rates):
            result[s][f][r] = int(a[count])
            count += 1

for s in range(switches):
    for f in range(flows):
        if result[s][f][0] == 1:
            result[s][f][1] = 0
            result[s][f][2] = 0
        if result[s][f][1] == 1:
            result[s][f][2] = 0
        for r in range(rates):
            if result[s][f][r] == 1:
                total_accuracy += accuracy[s][f][r]
                total_cost += RC[s][f][r]
    print result[s]

print 'accuracy:', total_accuracy
print 'cost:', total_cost
