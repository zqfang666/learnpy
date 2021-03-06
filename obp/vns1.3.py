# -*- coding: utf-8 -*-

# 生成一组订单，100个order，每个order仅含有一个item，并有item对应location数据
# 数据格式：【order#, aisle#, position#】
# 单区块仓库的布局：仓库是10*40（40 for each side，共800个储位）
# 共有10个aisle，采用ABC分类存储
# #1、2含有50%的demand items， #3,4,5含有35%的demand items, 剩余通道含有15%的demand items

import random
import pandas as pd
import numpy as np
import pickle
import copy
from itertools import combinations

import time

from obp.picker import Picker
from obp.batch import Batch
from obp.opt_best import opt_best


def prod_order(n=100):
    a_aisles = [1, 2]
    b_aisles = [3, 4, 5]
    c_aisles = [6, 7, 8, 9, 10]
    a, b = 0.5, 0.35
    order_list = []
    random.seed(1)
    for i in range(n):
        m = random.randint(1, 5)
        for _ in range(m):
            p = random.random()
            if p <= a:
                aisle = random.choice(a_aisles)
            elif p <= a + b:
                aisle = random.choice(b_aisles)
            else:
                aisle = random.choice(c_aisles)
            position = random.randint(1, 40)
            order_data = ('o' + str(i + 1).zfill(3), aisle, position)
            order_list.append(order_data)
    df = pd.DataFrame(data=order_list, columns=['order', 'aisle', 'position'])
    # df.to_csv('./data/orders15.csv', index=False)
    return df


def proc_time(df, para='s'):
    num_item = len(df)
    if para == 's':
        travel = s_shape(df)
    else:
        travel = opt_best(df)
    pt = 3 + num_item / 4 + travel / 20
    # center = (np.mean(df['aisle']), np.mean(df['position']))
    return pd.Series({'weight': num_item, 'pt': pt})


def s_shape(df):
    h_unit = 5
    v_unit = 40
    aisle_lst = sorted(set(df['aisle']))
    max_a = max(aisle_lst)
    num_a = len(aisle_lst)
    if num_a % 2 != 0:
        pos = max(df[df['aisle'] == max_a]['position'])
        travel = 2 + (max_a - 1) * h_unit * 2 + (num_a - 1) * v_unit + pos * 2
    else:
        travel = 2 + (max_a - 1) * h_unit * 2 + num_a * v_unit
    return travel



# objective functions
def tard(df, jobs):
    # 计算Tardiness与tardy jobs
    tardiness = 0
    tardy_jobs = 0
    for job in jobs:
        # print('Picker', job.p)
        # count = 0
        for batch in job.batches:
            # print('Batch' + str(count), batch.weight)
            # count += 1
            ct = batch.sd + batch.pt
            for order in batch.orders:
                dt = df.loc[order, 'dt']
                # weight = df.loc[order, 'weight']
                # print(order, weight, ct, dt, max(0, ct - dt))
                if ct > dt:
                    tardiness += ct - dt
                    tardy_jobs += 1
    # return tardy_jobs, tardiness
    return tardiness, tardy_jobs


def neighbor_l(s_inc, df_items, df_orders, C, l=1):
    neighbors = []
    # OSH1
    if l == 1:
        for picker in s_inc:
            for b1 in picker.batches:
                other_batches = picker.batches[:b1.b] + picker.batches[b1.b+1:]
                for order in b1.orders:
                    # print(order)
                    weight = df_orders.loc[order, 'weight']
                    shifted = False
                    for b2 in other_batches:
                        # print(b1.b, b1.orders, b2.b, b2.orders)
                        if weight <= C - b2.weight:
                            neighbor = copy.deepcopy(s_inc)
                            neighbor[picker.p].batches[b1.b].shift(order, weight, neighbor[picker.p].batches[b2.b])
                            neighbor[picker.p].re_routing(df_items)
                            neighbors.append(neighbor)
                        # elif not shifted:
                        #     neighbor = copy.deepcopy(s_inc)
                        #     neighbor[picker.p].batches[b1.b].delete(order, weight)
                        #     b_new = len(neighbor[picker.p].batches)
                        #     neighbor[picker.p].batches.append(Batch(b=b_new, weight=weight, orders=[order]))
                        #     neighbor[picker.p].re_routing(df_items)
                        #     neighbors.append(neighbor)
                        #     shifted = True
    # OSW1
    elif l == 2:
        for picker in s_inc:
            for b1, b2 in combinations(picker.batches, 2):
                for order1 in b1.orders:
                    w1 = df_orders.loc[order1, 'weight']
                    for order2 in b2.orders:
                        w2 = df_orders.loc[order2, 'weight']
                        neighbor = copy.deepcopy(s_inc)
                        if b1.weight - w1 + w2 <= C and b2.weight + w1 - w2 <= C:
                            neighbor[picker.p].batches[b1.b].swap(order1, order2, w1, w2, neighbor[picker.p].batches[b2.b])
                        # elif b1.weight - w1 + w2 > C:  # 可证明 b2.weight + w1 - w2<=C
                        #     neighbor[picker.p].batches[b2.b].delete(order2, w2)
                        #     neighbor[picker.p].batches[b1.b].shift(order1, w1, neighbor[picker.p].batches[b2.b])
                        #     b_new = len(neighbor[picker.p].batches)
                        #     neighbor[picker.p].batches.append(Batch(b=b_new, weight=w2, orders=[order2]))
                        # else:
                        #     neighbor[picker.p].batches[b1.b].delete(order1, w1)
                        #     neighbor[picker.p].batches[b2.b].shift(order2, w2, neighbor[picker.p].batches[b1.b])
                        #     b_new = len(neighbor[picker.p].batches)
                        #     neighbor[picker.p].batches.append(Batch(b=b_new, weight=w1, orders=[order1]))
                            neighbor[picker.p].re_routing(df_items)
                            neighbors.append(neighbor)
    else:
        pass
    return neighbors


def run(p_max, N, C, mtcr):
    # N = 15
    # C = 7
    # # modified traffic congestion rates
    # p_max = 2
    # mtcr = 0.7
    df_items = prod_order(n=N)
    # df_items = pd.read_csv(r'./data/orders15.csv')
    # # 采用不同的Routing strategy会产生不同的路径
    # # 采用S-shape策略，分奇数通道与偶数通道两种情况处理
    df_orders = prod_due_dates(df_items, mtcr, p_max)
    # df_orders = pd.read_csv('./data/due_dates0.7.csv', index_col=0)
    df_orders = df_orders.sort_values(by=['dt'], ascending=True)

    # 采用Earliest Start Date方法生成初始解
    # 还要计算出Tardiness.
    s_ini = init_solution(C, df_items, df_orders, p_max)
    # with open(r'./data/jobs.pkl', 'wb') as file:
    #     pickle.dump(jobs, file)
    # 已经产生initial solutions，下一步产生临域解，先考虑bsw2
    # 可以将其看作Picker的一个方法，Picker与另外一个Picker交换Batch
    tardy_pair_inc = tard(df_orders, s_ini)

    s_inc = local_search(C, df_items, df_orders, s_ini)
    M = 10
    for m in range(M):
        # print(m)
        l = 1
        while l <= 4:
            tardy_pair_inc = tard(df_orders, s_inc)
            # print(p_max, N, C, mtcr, tardy_pair_inc)
            # generate a solution s' at random N_l(s_inc) shaking phase
            # s_rand = rand_neighbor(l=l)
            s_rand = rand_neighbor(C, df_items, df_orders, s_inc, l=l)
            s_star = local_search(C, df_items, df_orders, s_rand)
            tardy_pair_star = tard(df_orders, s_star)
            if tardy_pair_star < tardy_pair_inc:
                s_inc = s_star
                l = 1
            else:
                l += 1
    print(p_max, N, C, mtcr, tardy_pair_inc)
    return s_inc


def rand_neighbor(C, df_items, df_orders, s_inc, l):
    # OSW2
    if l == 1:
        p1, p2 = random.sample(s_inc, 2)
        b1, b2 = random.choice(p1.batches), random.choice(p2.batches)
        order1, order2 = random.choice(b1.orders), random.choice(b2.orders)
        w1 = df_orders.loc[order1, 'weight']
        w2 = df_orders.loc[order2, 'weight']
        neighbor = copy.deepcopy(s_inc)
        if b1.weight - w1 + w2 <= C and b2.weight + w1 - w2 <= C:
            neighbor[p1.p].batches[b1.b].swap(order1, order2, w1, w2,
                                              neighbor[p2.p].batches[b2.b])
        elif b1.weight - w1 + w2 > C:  # 可证明 b2.weight + w1 - w2<=C
            neighbor[p2.p].batches[b2.b].delete(order2, w2)
            neighbor[p1.p].batches[b1.b].shift(order1, w1, neighbor[p2.p].batches[b2.b])
            b_new = len(neighbor[p1.p].batches)
            neighbor[p1.p].batches.append(Batch(b=b_new, weight=w2, orders=[order2]))
        else:
            neighbor[p1.p].batches[b1.b].delete(order1, w1)
            neighbor[p2.p].batches[b2.b].shift(order2, w2, neighbor[p1.p].batches[b1.b])
            b_new = len(neighbor[p2.p].batches)
            neighbor[p2.p].batches.append(Batch(b=b_new, weight=w1, orders=[order1]))
        neighbor[p1.p].re_routing(df_items)
        neighbor[p2.p].re_routing(df_items)
    # OSH2
    elif l == 2:
        p1, p2 = random.sample(s_inc, 2)
        b1, b2 = random.choice(p1.batches), random.choice(p2.batches)
        order = random.choice(b1.orders)
        weight = df_orders.loc[order, 'weight']
        if weight <= C - b2.weight:
            neighbor = copy.deepcopy(s_inc)
            neighbor[p1.p].batches[b1.b].shift(order, weight, neighbor[p2.p].batches[b2.b])
            neighbor[p1.p].re_routing(df_items)
            neighbor[p2.p].re_routing(df_items)
        else:
            neighbor = copy.deepcopy(s_inc)
            neighbor[p1.p].batches[b1.b].delete(order, weight)
            b_new = len(neighbor[p2.p].batches)
            neighbor[p2.p].batches.append(Batch(b=b_new, weight=weight, orders=[order]))
            neighbor[p1.p].re_routing(df_items)
            neighbor[p2.p].re_routing(df_items)
    # BSW2
    elif l == 3:
        p1, p2 = random.sample(s_inc, 2)
        k1, k2 = len(p1.batches), len(p2.batches)
        i, j = random.randint(0, k1-1), random.randint(0, k2-1)
        neighbor = copy.deepcopy(s_inc)
        neighbor[p1.p].swap(neighbor[p2.p], i, j)
        # 对两边position在i, j后的pt和sd进行重新的调整
        neighbor[p1.p].tune()
        neighbor[p2.p].tune()
    # BSH2
    else:
        p1, p2 = random.sample(s_inc, 2)
        k1, k2 = len(p1.batches), len(p2.batches)
        i, j = random.randint(0, k1 - 1), random.randint(0, k2)
        neighbor = copy.deepcopy(s_inc)
        neighbor[p1.p].shift(neighbor[p2.p], i, j)
        neighbor[p1.p].tune()
        neighbor[p2.p].tune()

    return neighbor


def local_search(C, df_items, df_orders, s_inc):
    l = 1
    while l <= 2:
        tardy_pair_inc = tard(df_orders, s_inc)
        neighbors = neighbor_l(s_inc, df_items, df_orders, C, l=l)
        f_s = {}
        for solution in neighbors:
            tardy_pair = tard(df_orders, solution)
            f_s[tardy_pair] = solution
        if f_s:
            tardy_pair_star = min(f_s, key=lambda x: (x[0], x[1]))
            s_star = f_s[tardy_pair_star]
            if tardy_pair_star < tardy_pair_inc:
                s_inc = s_star
                l = 1
            else:
                l += 1
        else:
            l += 1
    return s_inc


def init_solution(C, df_items, df_orders, p_max):
    jobs = []
    sd_p = [0] * p_max
    for p in range(p_max):
        jobs.append(Picker(p, batches=[Batch(b=0, sd=0, pt=0, weight=0, orders=[])]))
    for row in df_orders.itertuples():
        order1, weight, pt = row.Index, row.weight, row.pt
        for picker in jobs:
            batch = picker.batches[-1]
            # 如果可以分配给last position batch， sd_p就是last batch 的sd
            if batch.weight + weight <= C:
                # CASE 1
                sd_p[picker.p] = (batch.sd, 1)
            else:
                # CASE 2
                ct = batch.sd + batch.pt
                sd_p[picker.p] = (ct, 2)
        p_star = sd_p.index(min(sd_p))
        case = sd_p[p_star][1]
        if case == 2:
            prev = jobs[p_star].batches[-1]
            sd = prev.sd + prev.pt
            b = len(jobs[p_star].batches)
            jobs[p_star].batches.append(Batch(b=b, sd=sd, pt=0, weight=0, orders=[]))
        batch = jobs[p_star].batches[-1]
        batch.orders.append(order1)
        # 一个batch里的所有orders需要合并在一起计算routing time，而不是pt单纯地相加！
        batch.routing_time(df_items, para='o')
        batch.weight += weight
    return jobs


def prod_due_dates(df_items, mtcr, p_max):
    df_orders = df_items.groupby(by=['order'])[['aisle', 'position']] \
        .apply(lambda x: proc_time(x, para='o'))
    min_pt, sum_pt = min(df_orders['pt']), sum(df_orders['pt'])
    max_pt = (2 * (1 - mtcr) * sum_pt + min_pt) / p_max
    random.seed(1)
    df_orders['dt'] = [round(random.uniform(min_pt, max_pt), 2) for _ in range(len(df_orders))]
    # df_orders.to_csv('./data/due_dates0.7.csv', index=False)
    return df_orders


def main():
    P_MAX = [2, 4]
    N = [50, 100]
    C = [10, 20]
    MTCR = [0.6, 0.7, 0.8]
    for p_max in P_MAX:
        for n in N:
            for c in C:
                for mtcr in MTCR:
                    a = time.time()
                    run(p_max, n, c, mtcr)
                    b = time.time()
                    print('time %.2f s' % (b - a))
    # s_inc = run(2, 15, 7, 0.7)
    # df_orders = pd.read_csv('./data/due_dates0.7.csv', index_col=0)
    # df = df_orders.sort_values(by=['dt'], ascending=True)
    # for job in s_inc:
    #     print('Picker', job.p)
    #     count = 0
    #     for batch in job.batches:
    #         print('Batch' + str(count), batch.weight)
    #         count += 1
    #         ct = batch.sd + batch.pt
    #         for order in batch.orders:
    #             dt = df.loc[order, 'dt']
    #             weight = df.loc[order, 'weight']
    #             print(order, weight, ct, dt, max(0, ct - dt))

    # with open(r'./data/jobs.pkl', 'rb') as file:
    #     jobs = pickle.load(file)


    print('ok')





if __name__ == '__main__':
    main()
