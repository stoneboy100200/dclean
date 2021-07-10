#!/usr/bin/env python
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import csv
import argparse
import os
import sys
import math
from matplotlib import font_manager as fm, rcParams
import plotly
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re

# compatible with Chinese fonts
plt.rcParams['font.sans-serif'] = 'SimHei'
plt.rcParams['axes.unicode_minus'] = False

def convert_csv(path, file):
    # remove the first line to avoid converting error (not utf8)
    os.system("sed -i -e '/Linux/d' " + path)
    with open(file, 'w+', newline='') as csvfile:
        csv_file = csv.writer(csvfile, dialect='excel')
        with open(path, 'r', encoding='utf-8') as filein:
            for line in filein:
                if line.split():
                    line_list = line.strip('\n').split()
                    csv_file.writerow(line_list)

def match_cpu_core(detail):
    cpu = {}
    def cpu_core(tgid_g, tid_g, core):
        if tid_g.isdigit():
            cpu.setdefault(tid_g, set()).add(core)
        elif tgid_g.isdigit():
            cpu.setdefault(tgid_g, set()).add(core)

    detail.apply(lambda row: cpu_core(row['tgid'], row['tid'], row['cpu']), axis = 1)
    return cpu

def gen_pidstat_thread_graph(data, thread, p_status, p_process, output):
    thread_data = filter_process(data, p_process)
    tid_data = thread_data[thread_data['tid'] == thread]
    if len(tid_data) != 0:
        fig = plt.figure(figsize = (20, 10))
        set_line_chart_param(tid_data, p_status, "Thread "+thread, 'CPU Usage(%)')
        plt.savefig(output + "/" + thread+".jpg", bbox_inches='tight')
        sys.exit(0)


def gen_data(data, thread, p_status, p_process, output):
    # delete rows that contain 'Average:'
    detail = data[~data.index.isin(['Average:'])]
    if len(thread) != 0:
        gen_pidstat_thread_graph(detail, thread, p_status, p_process, output)
    cpu = match_cpu_core(detail)

    # get rows that contain 'Average:'
    avg = data[data.index.isin(['Average:'])]
    avg = avg.reset_index(drop=True)
    avg = avg.drop(index=[0], axis = 0)

    def get_cpu_core(tgid, tid):
        return sorted(list(map(int, cpu[tid] if tid.isdigit() else cpu[tgid])))
    avg['cpu'] = avg.apply(lambda row: get_cpu_core(row['tgid'], row['tid']), axis = 1)
    return avg

def add_process(data):
    process = ""
    def get_process(tgid, command):
        global process
        if tgid.isdigit():
            process = command
        return process
    data['process'] = data.apply(lambda row: get_process(row['tgid'], row['command']), axis = 1)

def filter_process(data, p_process):
    data = data[data['tgid'].isin(['-'])]
    if len(p_process) != 0:
        data = data[data['process'].isin(p_process)]
    return data

def get_graph_data(data):
    data[['%usr', '%system', '%CPU']] = data[['%usr', '%system', '%CPU']].astype(float)
    process = data.groupby(data['Process'])[['%usr', '%system', '%CPU']].sum()
    x_list = process.index
    index = np.arange(len(x_list))
    y_list1 = round(process['%usr'], 2)
    y_list2 = round(process['%system'], 2)
    y_list3 = round(process['%CPU'], 2)
    return x_list, index, y_list1, y_list2, y_list3

def set_bar_chart_param(data, ax, title, cpu_status):
    bar_width=0.2
    data[cpu_status] = data[cpu_status].astype(float)
    process = data.groupby(data['process'])[cpu_status].sum()
    x_list = process.index
    index = np.arange(len(x_list))
    for i, status in enumerate(cpu_status):
        y_list = round(process[status], 1)
        rect = ax.bar(index+bar_width*i, y_list, bar_width, label = status)
        auto_text(rect, ax)

    ax.set_ylabel('CPU Usage(%)')
    ax.set_xticks(index + len(cpu_status)*bar_width/2 - bar_width/2)
    ax.set_xticklabels(x_list, rotation=10)
    ax.set_title(title)
    ax.set_ylim(0, 100)
    ax.legend()

def gen_pidstat_graph(data, cpu_status, title, output):
    graph_num = len(title)
    fig, axs = plt.subplots(graph_num, figsize = (20, graph_num*5))
    plt.subplots_adjust(hspace=0.4)
    for i, t in enumerate(title):
        set_bar_chart_param(data[i], axs[i], t, cpu_status)
    plt.savefig(output + "/pidstat_bar.jpg", bbox_inches = 'tight')

def auto_text(rects, ax):
    for rect in rects:
        height = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()/2, height+0.01*height, rect.get_height(), ha='center', va='bottom', fontsize=10)

def sort_by_cpu(data, core, cpu_status, output):
    # add a new column for length of 'CPU'
    data['len'] = data.apply(lambda row: len(row['cpu']), axis = 1)
    data = data.sort_values(by = 'len' , ascending = True)
    data_s = data.loc[data['len'] == 1].sort_values(by = 'cpu', ascending = True)
    data_m = data.loc[data['len'] != 1]
    data = data_s.append(data_m)

    # transform list to str
    data['cpu'] = data['cpu'].apply(lambda row: ','.join(str(i) for i in row))
    cpu_data = []
    title = []
    for i, cpu in enumerate(core):
        core_data = data[(data['cpu'].isin([cpu])) & (data['len'] == 1)]
        if len(core_data) != 0:
            cpu_data.append(core_data.sort_values(by = ['process', 'tid'], ascending = True))
            title.append('CPU'+cpu)

    cpu_unbound = data.loc[data['len'] != 1].sort_values(by = ['process', 'tid'], ascending = True)
    if len(cpu_unbound) != 0:
        cpu_data.append(cpu_unbound)
        title.append('Other_CPU')
    gen_pidstat_graph(cpu_data, cpu_status, title, output)
    data = pd.concat(cpu_data, axis = 0, ignore_index = True)
    data = data.drop(columns=['len'])
    return data

def set_line_chart_param(cpu_data, cpu_status, title, y_label):
    line_color = ['b', 'r', 'g', 'y', 'k', 'c', 'm', 'pink', 'darkred', 'olive', 'lime', 'deeppink']
    line_style = '-'
    x_num = 30
    x_step = 35

    if len(cpu_data.index) > x_num:
        x_step = int(len(cpu_data.index) / x_num)
    for i, status in enumerate(cpu_status):
        plt.plot(cpu_data.index, cpu_data[status].astype(float), color = line_color[i], linestyle = line_style)

    plt.xlabel('Time', fontsize = 12)
    plt.ylabel(y_label, fontsize = 12)
    plt.xticks(np.arange(0, len(cpu_data.index), x_step), cpu_data.iloc[np.arange(0, len(cpu_data.index), x_step), 0].index, rotation = 25)
    if title[0:3] == 'CPU' or title[0:6] == 'Thread':
        plt.ylim(0,100)
    plt.legend(cpu_status)
    plt.title(title)

def gen_mpstat_pie_graph(data, output, is_picture):
    data = data.apply(pd.to_numeric, errors = 'ignore')
    cpu_avg = round(data.groupby('cpu').agg('mean'), 2)
    # pie graph for all CPU
    cpu_avg.index = cpu_avg.index.map(lambda x:x.upper())
    row_cnt = math.ceil(len(cpu_avg.index) / 2)
    specs = [[{'type':'domain'}, {'type':'domain'}]] * row_cnt
    title = ['CPU ' + i for i in cpu_avg.index]
    fig = make_subplots(row_cnt, 2, specs = specs, subplot_titles = title)
    row = 1
    for i in range(0, len(title), 2):
        fig.add_trace(go.Pie(labels = cpu_avg.columns,
                             values = cpu_avg.iloc[i],
                             textinfo = 'label+percent',
                             name = title[i]), row, 1)
        if i == (len(title)-1) and len(title)%2 != 0:
            pass
        else:
            fig.add_trace(go.Pie(labels = cpu_avg.columns,
                                 values = cpu_avg.iloc[i+1],
                                 textinfo = 'label+percent',
                                 name = title[i+1]), row, 2)
        row += 1

    fig.update_layout(
        autosize = False,
        height = 400 * len(title),
        width=1800,
        title_text = 'Average CPU Usage')
    if not is_picture:
        fig.write_html(output + '/' + 'mpstat_pie.html')
    else:
        fig.write_image(output + '/' + 'mpstat_pie.jpg', width = 1500, height = 400*len(title))

def gen_mpstat_graph(data, core, cpu_status, output, is_picture):
    detail = data[~data.index.isin(['Average:'])]
    gen_mpstat_pie_graph(detail, output, is_picture)

    graph_num = len(core)
    fig = plt.figure(figsize = (20, graph_num*5))
    plt.subplots_adjust(hspace = 0.4)
    for i, cpu in enumerate(core):
        cpu_data = detail[detail['cpu'].isin([cpu])]
        if len(cpu_data) != 0:
            subgraph_pos = str(graph_num) + '1' + str(i+1)
            plt.subplot(int(subgraph_pos))
            plt.grid(linestyle = '--')
            set_line_chart_param(cpu_data, cpu_status, 'CPU'+cpu, 'CPU Usage(%)')
        else:
            print("[Warning] CPU core is invalid")

    plt.savefig(output + "/mpstat_line.jpg", bbox_inches='tight')

def gen_sunburst_graph(data, output, is_picture):
    data['command']=data['command'].map(lambda x: x[3:] if x[0:3]=='|__' else x)
    data['%cpu']=data['%cpu'].map(lambda x: str(x)+'%')
    fig = px.sunburst(data, path = ['cpu', 'process', 'command', 'tid', '%cpu'])
    fig.update_layout()
    if not is_picture:
        fig.write_html(output + '/' + 'pidstat_sunburst.html')
    else:
        fig.write_image(output + '/' + 'pidstat_sunburst.jpg', width = 1000, height = 1000)

def gen_pidstat_cpu_graph(data, p_status, thread, p_process, output, core, is_picture):
    data.dropna(axis = 0, how = 'any', inplace = True)
    cpu_status = ['%'+i for i in p_status]
    avg = gen_data(data, thread, cpu_status, p_process, output)
    add_process(avg)
    # remove row of main process
    avg = filter_process(avg, p_process)
    avg = sort_by_cpu(avg, core, cpu_status, output)
    gen_sunburst_graph(avg, output, is_picture)
    file = 'pidstat_cpu.csv'
    avg.to_csv(output + '/' + file, index = False)

def gen_pidstat_io_graph(data, p_process, output, is_picture):
    detail = data[~data.index.isin(['#'])]
    column = detail.columns.tolist()
    detail = detail.copy()
    detail.dropna(axis = 1, how = 'all', inplace = True)
    detail.dropna(axis = 0, how = 'any', inplace = True)
    if 'time' in column:
        column.remove('time')
    detail.columns = column
    file = 'pidstat_io.csv'
    detail.to_csv(output + '/' + file, index = False)
    data_g = detail.groupby('command', sort = False)
    if len(p_process) != 0:
        processes = p_process
    else:
        processes = data_g.size().index

    title = []
    for i, c in enumerate(processes):
        title.append('Read from Disk by ' + c)
        title.append('Write to Disk by ' + c)
    title.append('CCWR')
    title.append('IO Delay')
    fig = make_subplots(rows=len(processes)+1, cols=2, subplot_titles=title)

    for i, c in enumerate(processes):
        fig.add_trace(go.Scatter(x = detail.loc[detail['command'] == c].index,
                                 y = detail.loc[detail['command'] == c]['kb_rd/s'],
                                 mode = 'lines',
                                 fill = 'tozeroy',
                                 showlegend = False),
                      row = i+1, col = 1)
        fig.add_trace(go.Scatter(x = detail.loc[detail['command'] == c].index,
                                 y = detail.loc[detail['command'] == c]['kb_wr/s'],
                                 mode = 'lines',
                                 fill = 'tozeroy',
                                 showlegend = False),
                      row = i+1, col = 2)
        fig.update_yaxes(title_text = 'Read(kb/s)', row = i+1, col = 1)
        fig.update_yaxes(title_text = 'Write(kb/s)', row = i+1, col = 2)
        fig.update_xaxes(title_text = 'Time', row = i+1, col = 1)
        fig.update_xaxes(title_text = 'Time', row = i+1, col = 2)

    color = px.colors.qualitative.Plotly
    index = 0
    # display kB_ccwr/s and iodelay
    for c, d in data_g:
        if 'kb_ccwr/s' in detail.columns:
            fig.add_trace(go.Scatter(x = d.index,
                                     y = d['kb_ccwr/s'],
                                     mode = 'lines',
                                     fill = 'tozeroy',
                                     name = c,
                                     line_color = color[index],
                                     legendgroup = c),
                          row = len(processes)+1, col = 1)
        if 'iodelay' in detail.columns:
            fig.add_trace(go.Scatter(x = d.index,
                                     y = d['iodelay'],
                                     mode = 'lines',
                                     fill = 'tozeroy',
                                     name = c,
                                     line_color = color[index],
                                     legendgroup = c,
                                     showlegend = False,),
                          row = len(processes)+1, col = 2)
        index += 1
    if 'kb_ccwr/s' in detail.columns:
        fig.update_yaxes(title_text = 'CCWR(kb/s)', row = len(processes)+1, col = 1)
        fig.update_xaxes(title_text = 'Time', row = len(processes)+1, col = 1)
    if 'iodelay' in detail.columns:
        fig.update_yaxes(title_text = 'Clock Cycle', row = len(processes)+1, col = 2)
        fig.update_xaxes(title_text = 'Time', row = len(processes)+1, col = 2)

    fig.update_layout(title = 'IO Usage',
                      height = 500*len(processes),
                      legend = {'x': 1, 'y': 0})
    if not is_picture:
        fig.write_html(output + '/' + 'pidstat_io.html')
    else:
        fig.write_image(output + '/' + 'pidstat_io.jpg', width = 1500, height = 500*len(processes))

def gen_pidstat_mem_graph(data, p_process, output, is_picture):
    detail = data[~data.index.isin(['#'])]
    column = detail.columns.tolist()
    detail = detail.copy()
    detail.dropna(axis = 1, how = 'all', inplace = True)
    detail.dropna(axis = 0, how = 'any', inplace = True)
    if 'time' in column:
        column.remove('time')
    detail.columns = column
    # convert kb to M
    detail['vsz'] = detail['vsz'].map(lambda x: float(x)/1024)
    detail['rss'] = detail['rss'].map(lambda x: float(x)/1024)
    file = 'pidstat_mem.csv'
    detail.to_csv(output + '/' + file, index = False)
    data_g = detail.groupby('command', sort = False)
    if len(p_process) != 0:
        processes = p_process
    else:
        processes = data_g.size().index

    title = []
    for i, c in enumerate(processes):
        title.append('VSZ of ' + c)
        title.append('RSS of ' + c)
    title.append('Memory Usage Percentages')
    fig = make_subplots(rows=len(processes)+1, cols=2, subplot_titles=title)

    for i, c in enumerate(processes):
        fig.add_trace(go.Scatter(x = detail.loc[detail['command'] == c].index,
                                 y = detail.loc[detail['command'] == c].vsz,
                                 mode = 'lines',
                                 fill = 'tozeroy',
                                 showlegend = False),
                      row = i+1, col = 1)
        fig.add_trace(go.Scatter(x = detail.loc[detail['command'] == c].index,
                                 y = detail.loc[detail['command'] == c].rss,
                                 mode = 'lines',
                                 fill = 'tozeroy',
                                 showlegend = False),
                      row = i+1, col = 2)
        fig.update_yaxes(title_text = 'VSZ(M)', row = i+1, col = 1)
        fig.update_yaxes(title_text = 'RSS(M)', row = i+1, col = 2)
        fig.update_xaxes(title_text = 'Time', row = i+1, col = 1)
        fig.update_xaxes(title_text = 'Time', row = i+1, col = 2)

    color = px.colors.qualitative.Plotly
    index = 0
    # display %mem
    for c, d in data_g:
        if '%mem' in detail.columns:
            fig.add_trace(go.Scatter(x = d.index,
                                     y = d['%mem'],
                                     mode = 'lines',
                                     fill = 'tozeroy',
                                     name = c,
                                     line_color = color[index]),
                          row = len(processes)+1, col = 1)
            index += 1
    if '%mem' in detail.columns:
        fig.update_yaxes(title_text = 'Mem(%)', row = len(processes)+1, col = 1)
        fig.update_xaxes(title_text = 'Time', row = len(processes)+1, col = 1)

    fig.update_layout(title = 'Memory Usage',
                      height = 500*len(processes),
                      legend = {'x': 0.5, 'y': 0})
    if not is_picture:
        fig.write_html(output + '/' + 'pidstat_mem.html')
    else:
        fig.write_image(output + '/' + 'pidstat_mem.jpg', width = 1500, height = 500*len(processes))

def pidstat_process(pidstat_path, core, thread, p_status, p_process, output, pidstat_t, pidstat_r, pidstat_d, is_picture):
    if not os.path.exists(pidstat_path):
        print("[Error] {} does not exist!".format(pidstat_path))
        sys.exit(1)
    print("pidstat_path={}".format(pidstat_path))

    # convert to csv file
    file = 'pidstat.csv'
    convert_csv(pidstat_path, output + '/' + file)
    data = pd.read_csv(output + '/' + file, header = 0, index_col = 0)
    data.columns = data.columns.map(lambda x:x.lower())

    if pidstat_t:
        gen_pidstat_cpu_graph(data, p_status, thread, p_process, output, core, is_picture)
    if pidstat_r:
        gen_pidstat_mem_graph(data, p_process, output, is_picture)
    if pidstat_d:
        gen_pidstat_io_graph(data, p_process, output, is_picture)

def mpstat_process(mpstat_path, core, m_status, output, is_picture):
    if not os.path.exists(mpstat_path):
        print("[Error] {} does not exist!".format(mpstat_path))
        sys.exit(1)
    print("mpstat_path={}".format(mpstat_path))

    # convert to csv file
    file = 'mpstat.csv'
    convert_csv(mpstat_path, output + '/' + file)
    data = pd.read_csv(output + '/' + file, header=0, index_col=0)
    data.dropna(axis = 0, how = 'any', inplace = True)
    data.columns = data.columns.map(lambda x:x.lower())
    data = data[data['cpu'] != 'CPU']
    data.to_csv(output + '/' + file, index = False)

    cpu_status = ['%'+i for i in m_status]
    gen_mpstat_graph(data, core, cpu_status, output, is_picture)

def gen_vmstat_graph(data, v_status, title, y_label, output):
    graph_num = len(title)
    fig = plt.figure(figsize = (20, 10))
    plt.subplots_adjust(hspace = 0.6)
    for i, t in enumerate(title):
        subgraph_pos = str(graph_num) + '1' + str(i+1)
        plt.subplot(int(subgraph_pos))
        plt.grid(linestyle = '--')
        set_line_chart_param(data, v_status[i], title[i], y_label[i])
        if t == 'Memory':
            plt.axhline(y = 20, c = "black", ls = "--", lw = 1)
            plt.axhline(y = 100, c = "black", ls = "--", lw = 1)

    plt.savefig(output + "/vmstat_line.jpg", bbox_inches='tight')

def vmstat_process(vmstat_path, vmstat_mem, vmstat_io, vmstat_system, vmstat_cpu, output):
    if not os.path.exists(vmstat_path):
        print("[Error] {} does not exist!".format(vmstat_path))
        sys.exit(1)
    print("vmstat_path={}".format(vmstat_path))

    # convert to csv file
    file = 'vmstat.csv'
    convert_csv(vmstat_path, output + '/' + file)
    data = pd.read_csv(output + '/' + file, header=1)
    data.dropna(axis = 0, how = 'any', inplace = True)
    data.columns = data.columns.map(lambda x:x.lower())
    v_data = data[data.r.apply(lambda x: x.isnumeric())]
    v_data = v_data.copy()
    v_data['swpd'] = v_data['swpd'].map(lambda x: float(x)/1024)
    v_data['free'] = v_data['free'].map(lambda x: float(x)/1024)
    v_data['buff'] = v_data['buff'].map(lambda x: float(x)/1024)
    v_data['cache'] = v_data['cache'].map(lambda x: float(x)/1024)

    title = []
    v_status = []
    y_label = []
    if vmstat_mem:
        title.append('Memory')
        v_status.append(['swpd', 'free', 'buff', 'cache'])
        y_label.append('Mem Usage(M)')
    if vmstat_io:
        title.append('IO')
        v_status.append(['bi', 'bo'])
        y_label.append('IO Usage(Blocks/s)')
    if vmstat_system:
        title.append('System')
        v_status.append(['in', 'cs'])
        y_label.append('System Usage(Times/s)')
    if vmstat_cpu:
        title.append('CPU')
        v_status.append(['us', 'sy', 'id', 'wa', 'st'])
        y_label.append('CPU Usage(%)')
    gen_vmstat_graph(v_data, v_status, title, y_label, output)

def filter_log(path, output, pattern):
    org_output = sys.stdout
    with open(path, 'r', encoding='UTF-8',errors='ignore') as f:
        output_file = open(output, 'w')
        sys.stdout = output_file
        res = re.compile(pattern)
        for line in f:
            m = res.match(line)
            if m is not None:
                print(line)
        output_file.close()
    sys.stdout = org_output

def tcmalloc_process(tcmalloc_path, output, is_picture):
    if not os.path.exists(tcmalloc_path):
        print("[Error] {} does not exist!".format(tcmalloc_path))
        sys.exit(1)
    print("tcmalloc_path={}".format(tcmalloc_path))

    tcmalloc_file = 'tcmalloc.log'
    filter_log(tcmalloc_path, output+'/'+tcmalloc_file, r'(.*)(^TCMALLOC_MINI\(USER\).*thread_one \d)')
    # convert to csv file
    file = 'tcmalloc.csv'
    convert_csv(output+'/'+tcmalloc_file, output + '/' + file)
    column = ['c1', 'c2', 'c3', 'mem', 'c4', 'c5', 'c6', 'c7', 'c8', 'tid', 'c10', 'c11', 'c12', 'c13']
    data = pd.read_csv(output + '/' + file, header = 0, index_col = 0,
                       names = column)
    data.dropna(axis = 0, how = 'any', inplace = True)
    data_g = data.groupby('tid', sort = False)

    fig = make_subplots(rows=len(data_g.size().index), cols=1, subplot_titles=list(map(str, data_g.size().index)))
    idx = 1
    for c, d in data_g:
        fig.add_trace(go.Scatter(x = np.arange(0, len(d['mem'])),
                                 y = d['mem'],
                                 fill = 'tozeroy',
                                 name = c),
                      row = idx, col = 1)
        fig.update_xaxes(title_text = 'Time', row = idx, col = 1)
        fig.update_yaxes(title_text = 'Mem Size(M)', row = idx, col = 1)
        idx += 1
    fig.update_layout(title = 'Memory Usage of Thread', height = 500*len(data_g.size().index))
    if not is_picture:
        fig.write_html(output + '/' + 'tcmalloc.html')
    else:
        fig.write_image(output + '/' + 'tcmalloc.jpg', width = 1500, height = 500*len(data_g.size().index))

def time_column(data, column):
    data[column] = data[column].astype(str)
    
    if len(data.loc[data[column].str.contains(':') & ~data[column].str.endswith(':')]) != 0:
        # add new column for time
        time = ''
        def get_time(data):
            global time
            if data.find(':') != -1 and not data.endswith(':'):
                time = data
            return time
        data['time'] = data.apply(lambda row: get_time(row[column]), axis = 1)

def procrank_process(procrank_path, output, p_process, is_picture):
    if not os.path.exists(procrank_path):
        print("[Error] {} does not exist!".format(procrank_path))
        sys.exit(1)
    print("procrank_path={}".format(procrank_path))

    # convert to csv file
    file = 'procrank.csv'
    convert_csv(procrank_path, output + '/' + file)
    column = ['pid', 'vss', 'rss', 'pss', 'uss', 'command']
    data = pd.read_csv(output + '/' + file, names = column)

    time_column(data, 'pid')
    data.dropna(axis = 0, how = 'any', inplace = True)
    data['vss'] = data['vss'].apply(lambda row: float(row.rstrip('K'))/1024)
    data['rss'] = data['rss'].apply(lambda row: float(row.rstrip('K'))/1024)
    data['pss'] = data['pss'].apply(lambda row: float(row.rstrip('K'))/1024)
    data['uss'] = data['uss'].apply(lambda row: float(row.rstrip('K'))/1024)

    data_g = data.groupby('command', sort = False)
    if len(p_process) != 0:
        processes = p_process
    else:
        processes = data_g.size().index

    title = []
    for i, c in enumerate(processes):
        title.append('PSS of ' + c)
        title.append('USS of ' + c)
    fig = make_subplots(rows=len(processes), cols=2, subplot_titles=title)

    for i, c in enumerate(processes):
        data_x = data.loc[data['command'] == c].time if 'time' in data.columns \
            else np.arange(0, len(data.loc[data['command'] == c]))
        fig.add_trace(go.Scatter(x = data_x,
                                 y = data.loc[data['command'] == c].pss,
                                 mode = 'lines',
                                 fill = 'tozeroy',
                                 showlegend = False),
                      row = i+1, col = 1)
        fig.add_trace(go.Scatter(x = data_x,
                                 y = data.loc[data['command'] == c].uss,
                                 mode = 'lines',
                                 fill = 'tozeroy',
                                 showlegend = False),
                      row = i+1, col = 2)
        fig.update_yaxes(title_text = 'PSS(M)', row = i+1, col = 1)
        fig.update_yaxes(title_text = 'USS(M)', row = i+1, col = 2)
        fig.update_xaxes(title_text = 'Time', row = i+1, col = 1)
        fig.update_xaxes(title_text = 'Time', row = i+1, col = 2)

    fig.update_layout(title = 'Procrank Statistics', height = 500*len(processes))
    if not is_picture:
        fig.write_html(output + '/' + 'procrank.html')
    else:
        fig.write_image(output + '/' + 'procrank.jpg', width = 1500, height = 500*len(processes))

def free_process(free_path, output, is_picture):
    if not os.path.exists(free_path):
        print("[Error] {} does not exist!".format(free_path))
        sys.exit(1)
    print("free_path={}".format(free_path))

    # convert to csv file
    file = 'free.csv'
    convert_csv(free_path, output + '/' + file)
    column = ['type', 'total', 'used', 'free', 'shared', 'buff/cache', 'available']
    data = pd.read_csv(output + '/' + file, names = column)

    time_column(data, 'type')
    data.columns = data.columns.map(lambda x:x.lower())
    data.dropna(axis = 0, how = 'any', inplace = True)
    data['available'] = data['available'].apply(lambda row: float(row)/1024)
    data_x = data.loc[data['type'] == 'Mem:'].time if 'time' in data.columns \
            else np.arange(0, len(data.loc[data['type'] == 'Mem:'].available))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x = data_x,
                             y = data.loc[data['type'] == 'Mem:'].available,
                             mode = 'lines',
                             fill = 'tozeroy',
                             name = 'available',
                             connectgaps=True))
    fig.update_layout(title = 'Available Memory Statistics',
                      xaxis_title = 'Time',
                      yaxis_title = 'Available Memory(M)')

    if not is_picture:
        fig.write_html(output + '/' + 'free.html')
    else:
        fig.write_image(output + '/' + 'free.jpg')

def hogs_process(hogs_path, output, thread, is_picture):
    if not os.path.exists(hogs_path):
        print("[Error] {} does not exist!".format(hogs_path))
        sys.exit(1)
    print("hogs_path={}".format(hogs_path))

    # convert to csv file
    file = 'hogs.csv'
    convert_csv(hogs_path, output + '/' + file)
    column = ['PID', 'NAME', 'MSEC', 'PIDS', 'SYS', 'MEMORY', 'MEM%']
    data = pd.read_csv(output + '/' + file, names = column)

    data.columns = data.columns.map(lambda x:x.lower())
    data['sys'] = data['sys'].apply(lambda row: row.rstrip('%'))
    if len(thread) != 0:
        data = data[data['pid'] == int(thread)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x = np.arange(0, len(data['sys'])),
                             y = data['sys'],
                             mode = 'lines',
                             fill = 'tozeroy',
                             name = 'available',
                             connectgaps=True))
    fig.update_layout(title = 'mfrlaunch CPU Usage Statistics',
                      xaxis_title = 'Time',
                      yaxis_title = 'CPU Used(%)')

    if not is_picture:
        plotly.offline.plot(fig, filename = output + '/hogs.html')
    else:
        fig.write_image(output + '/' + 'hogs.jpg')

def main(args):
    pidstat_path = args.pidstat
    pidstat_t = args.pidstat_t
    pidstat_r = args.pidstat_r
    pidstat_d = args.pidstat_d
    p_status = args.p_status
    p_process = args.p_process
    thread = args.thread

    mpstat_path = args.mpstat
    m_status = args.m_status

    vmstat_path = args.vmstat
    vmstat_mem = args.vmstat_mem
    vmstat_io = args.vmstat_io
    vmstat_system = args.vmstat_system
    vmstat_cpu = args.vmstat_cpu

    core = args.core
    output = args.output

    tcmalloc_path = args.tcmalloc
    procrank_path = args.procrank
    free_path = args.free
    is_picture = args.picture
    hogs_path = args.hogs

    if len(output) == 0:
        output = os.getcwd()
    else:
        if not os.path.exists(output):
            print("[Error] {} does not exist!".format(output))
            sys.exit(1)
    print("output={}".format(output))

    if len(pidstat_path) != 0:
        pidstat_process(pidstat_path, core, thread, p_status, p_process, output, pidstat_t, pidstat_r, pidstat_d, is_picture)
    if len(mpstat_path) != 0:
        mpstat_process(mpstat_path, core, m_status, output, is_picture)
    if len(vmstat_path) != 0:
        vmstat_process(vmstat_path, vmstat_mem, vmstat_io, vmstat_system, vmstat_cpu, output)
    if len(tcmalloc_path) != 0:
        tcmalloc_process(tcmalloc_path, output, is_picture)
    if len(procrank_path) != 0:
        procrank_process(procrank_path, output, p_process, is_picture)
    if len(free_path) != 0:
        free_process(free_path, output, is_picture)
    if len(hogs_path) != 0:
        hogs_process(hogs_path, output, thread, is_picture)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data cleaning and visualization tools.")
    parser.add_argument("-p", "--pidstat", type=str, default="", help="Path of pidstat log.")
    parser.add_argument("-pt", "--pidstat_t", action='store_true', default=False, help="Display statistics for threads associated with selected tasks.")
    parser.add_argument("-pr", "--pidstat_r", action='store_true', default=False, help="Display statistics for memory utilization.")
    parser.add_argument("-pd", "--pidstat_d", action='store_true', default=False, help="Display I/O statistics.")
    parser.add_argument("-ps", "--p_status", type=str, default=['usr', 'system', 'cpu'], nargs='*', help="The status of pidstat. eg. usr system.")
    parser.add_argument("-pp", "--p_process", type=str, default=[], nargs='*', help="The process that needs to be displayed.")
    parser.add_argument("-m", "--mpstat", type=str, default="", help="Path of mpstat log.")
    parser.add_argument("-ms", "--m_status", type=str, default=['usr', 'sys', 'iowait', 'idle'], nargs='*', help="The status of mpstat. eg. usr sys idle")
    parser.add_argument("-v", "--vmstat", type=str, default="", help="Path of vmstat log.")
    parser.add_argument("-vm", "--vmstat_mem", action='store_true', default=True, help="Show memory status.")
    parser.add_argument("-vi", "--vmstat_io", action='store_true', default=False, help="Show io status.")
    parser.add_argument("-vs", "--vmstat_system", action='store_true', default=False, help="Show system status.")
    parser.add_argument("-vc", "--vmstat_cpu", action='store_true', default=False, help="Show cpu status.")
    parser.add_argument("-c", "--core", type=str, default=['0'], nargs='*', help="CPU core.")
    parser.add_argument("-t", "--thread", type=str, default="", help="Thread ID.")
    parser.add_argument("-o", "--output", type=str, default="", help="Path of output.")
    parser.add_argument("-tc", "--tcmalloc", type=str, default="", help="Path of tcmalloc log.")
    parser.add_argument("-pk", "--procrank", type=str, default="", help="Path of procrank log.")
    parser.add_argument("-f", "--free", type=str, default="", help="Path of free log.")
    parser.add_argument("-pic", "--picture", action='store_true', default=False, help="Save as picture.")
    parser.add_argument("-hg", "--hogs", type=str, default="", help="Path of hogs log for QNX.")
    args = parser.parse_args()
    main(args)
