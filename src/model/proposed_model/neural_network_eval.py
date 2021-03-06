# coding=utf-8
import csv
import datetime
import os
import random

import numpy as np
import sklearn
import tensorflow as tf

import performance_metrics as pm
import read_data
import rnn_config as config
from intensity import Intensity
from model import ProposedModel


def build_model(model_config):
    # input define
    max_time_stamp = model_config.max_time_stamp
    batch_size = model_config.batch_size
    x_depth = model_config.input_x_depth
    t_depth = model_config.input_t_depth

    with tf.name_scope('input'):
        placeholder_x = tf.placeholder('float64', [max_time_stamp, batch_size, x_depth])
        placeholder_t = tf.placeholder('float64', [max_time_stamp, batch_size, t_depth])
        intensity = Intensity(model_config)
        mutual_intensity = intensity.mutual_intensity_placeholder
    model = ProposedModel(model_config=model_config)

    placeholder_x, placeholder_t, loss, c_pred_list, mi = \
        model(placeholder_x=placeholder_x, placeholder_t=placeholder_t, mutual_intensity=mutual_intensity)

    return placeholder_x, placeholder_t, loss, c_pred_list, mi


def fine_tuning(train_config, node_list, data_object, summary_save_path, mutual_intensity_data, threshold):
    placeholder_x, placeholder_t, loss, c_pred_list, mi = node_list

    if train_config.optimizer == 'SGD':
        with tf.variable_scope('sgd', reuse=True):
            optimizer = tf.train.GradientDescentOptimizer
    else:
        raise ValueError('')

    global_step = tf.Variable(0, trainable=False)
    starter_learning_rate = train_config.learning_rate
    end_learning_rate = train_config.learning_rate / 100
    decay_steps = train_config.decay_step
    learning_rate = tf.train.polynomial_decay(starter_learning_rate, global_step,
                                              decay_steps, end_learning_rate,
                                              power=1)
    optimize_node = optimizer(learning_rate).minimize(loss)
    initializer = tf.global_variables_initializer()
    batch_count = data_object.get_batch_count()
    merged_summary = tf.summary.merge_all()

    saver = tf.train.Saver()
    train_metric_list = list()
    test_metric_list = list()

    with tf.Session() as sess:
        # sess = tf_debug.TensorBoardDebugWrapperSession(sess, 'Sunzhoujian:6064')
        # construct summary save path
        train_summary_save_path = os.path.join(summary_save_path, 'train')
        test_summary_save_path = os.path.join(summary_save_path, 'test')
        model_path = os.path.join(summary_save_path, 'model')
        os.makedirs(train_summary_save_path)
        os.makedirs(test_summary_save_path)
        os.makedirs(model_path)

        train_summary = tf.summary.FileWriter(train_summary_save_path, sess.graph)
        test_summary = tf.summary.FileWriter(test_summary_save_path, sess.graph)
        sess.run(initializer)

        for i in range(0, train_config.epoch):

            max_index = data_object.get_batch_count() + 1
            for j in range(0, max_index):
                # time major
                train_x, train_t = data_object.get_train_next_batch()
                max_time_stamp = len(train_x)

                train_dict = {placeholder_x: train_x, placeholder_t: train_t, mi: mutual_intensity_data}
                _ = sess.run([optimize_node], feed_dict=train_dict)

                if j % 10 == 0:
                    c_pred, summary = sess.run([c_pred_list, merged_summary], feed_dict=train_dict)
                    train_summary.add_summary(summary, i * batch_count + j)
                    metric_result = pm.performance_measure(c_pred, train_x[1:max_time_stamp], max_time_stamp - 1,
                                                           threshold)
                    train_metric_list.append([i, j, metric_result])

                # record metadata
                if i % 4 == 0 and j == 0:
                    run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
                    run_metadata = tf.RunMetadata()
                    _, _ = sess.run([c_pred_list, merged_summary],
                                    feed_dict=train_dict,
                                    options=run_options,
                                    run_metadata=run_metadata)
                    train_summary.add_run_metadata(run_metadata, 'step%d' % i)

            test_x, test_t = data_object.get_test_data()
            max_time_stamp = len(test_x)
            test_dict = {placeholder_x: test_x, placeholder_t: test_t, mi: mutual_intensity_data, }
            c_pred, summary = sess.run([c_pred_list, merged_summary], feed_dict=test_dict)
            metric_result = pm.performance_measure(c_pred, test_x[1:max_time_stamp], max_time_stamp - 1, threshold)
            test_metric_list.append([i, None, metric_result])
            test_summary.add_summary(summary, i * batch_count)

            if i == train_config.epoch / 2 or i == train_config.epoch - 1:
                saver.save(sess=sess, save_path=os.path.join(model_path, 'model'), global_step=i)

        # plot final roc_curve
        test_x, test_t = data_object.get_test_data()
        max_time_stamp = len(test_x) - 1
        test_dict = {placeholder_x: test_x, placeholder_t: test_t, mi: mutual_intensity_data}
        c_pred = sess.run([c_pred_list], feed_dict=test_dict)
        c_pred = np.reshape(c_pred, [1, -1])
        test_x = np.reshape(test_x[1:max_time_stamp], [1, -1])
        roc_curve = sklearn.metrics.roc_curve(test_x, c_pred)

    return train_metric_list, test_metric_list, roc_curve


def write_meta_data(train_meta, model_meta, path):
    with open(path + 'metadata.txt', 'w') as file:
        for key in train_meta:
            file.write(str(key) + ':' + str(train_meta[key]) + '\n')
        for key in model_meta:
            file.write(str(key) + ':' + str(model_meta[key]) + '\n')


def configuration_set():
    # fixed model parameters
    x_depth = 100
    t_depth = 1
    max_time_stamp = 5
    cell_type = 'revised_gru'
    c_r_ratio = 0
    activation = 'tanh'
    init_map = dict()
    init_map['gate_weight'] = tf.contrib.layers.xavier_initializer()
    init_map['candidate_weight'] = tf.contrib.layers.xavier_initializer()
    init_map['classification_weight'] = tf.contrib.layers.xavier_initializer()
    init_map['regression_weight'] = tf.contrib.layers.xavier_initializer()
    init_map['mutual_intensity'] = tf.contrib.layers.xavier_initializer()
    init_map['base_intensity'] = tf.contrib.layers.xavier_initializer()
    init_map['combine'] = tf.contrib.layers.xavier_initializer()

    init_map['candidate_bias'] = tf.initializers.zeros()
    init_map['classification_bias'] = tf.initializers.zeros()
    init_map['regression_bias'] = tf.initializers.zeros()
    init_map['gate_bias'] = tf.initializers.zeros()
    model_batch_size = None

    # fixed train parameters
    time = datetime.datetime.now().strftime("%H%M%S")
    root_path = os.path.abspath('..\\..\\..') + '\\model_evaluate\\Case_80_20\\'
    optimizer = 'SGD'
    mutual_intensity_path = os.path.join(root_path,
                                         'fourier_diagnosis_80_procedure_20_iteration_10_slot_1000_mutual_intensity'
                                         '.csv')
    # the parameter only effective when using SGD
    save_path = root_path + time + "\\"

    x_path = os.path.join(root_path, '20180816163944_100_x.npy')
    t_path = os.path.join(root_path, '20180816163944_100_t.npy')

    encoding = 'utf-8-sig'

    # random search parameter
    # batch_candidate = [64, 128, 256, 512]
    actual_batch_size = 128
    num_hidden_candidate = [32, 64, 128]
    num_hidden = num_hidden_candidate[random.randint(0, 2)]
    zero_state = np.zeros([num_hidden, ])
    learning_rate = 10 ** random.uniform(-1, 0)
    decay_step = 10000
    epoch = 200
    threshold_candidate = [0.6, 0.7, 0.8, 0.9]
    threshold = threshold_candidate[random.randint(0, 3)]
    pos_weight_candidate = [5, 10, 15, 20, 25, 30]
    pos_weight = pos_weight_candidate[random.randint(0, 5)]

    model_config = config.ModelConfiguration(x_depth=x_depth, t_depth=t_depth, max_time_stamp=max_time_stamp,
                                             num_hidden=num_hidden, cell_type=cell_type, c_r_ratio=c_r_ratio,
                                             activation=activation, zero_state=zero_state, init_map=init_map,
                                             batch_size=model_batch_size, threshold=threshold, pos_weight=pos_weight)
    train_config = config.TrainingConfiguration(optimizer=optimizer,
                                                save_path=save_path, actual_batch_size=actual_batch_size, epoch=epoch,
                                                decay_step=decay_step, learning_rate=learning_rate,
                                                mutual_intensity_path=mutual_intensity_path,
                                                file_encoding=encoding, t_path=t_path, x_path=x_path)
    return train_config, model_config


def read_time_decay(path, decay_length):
    time_decay = None

    with open(path, 'r', encoding='utf-8-sig') as file:
        csv_reader = csv.reader(file)
        for line in csv_reader:
            time_decay = line
            if len(time_decay) != decay_length:
                raise ValueError('')
            break

    return np.array(time_decay)


def validation_test():
    for i in range(0, 100):
        new_graph = tf.Graph()
        with new_graph.as_default():
            train_config, model_config = config.validate_configuration_set()
            threshold = model_config.threshold
            data_object = read_data.LoadData(train_config=train_config, model_config=model_config)
            key_node_list = build_model(model_config)
            mutual_intensity_data = \
                Intensity.read_mutual_intensity_data(encoding=train_config.encoding,
                                                     mutual_intensity_path=train_config.mutual_intensity_path,
                                                     size=model_config.input_x_depth)
            fine_tuning(train_config, key_node_list, data_object, train_config.save_path, mutual_intensity_data,
                        threshold)


def main():
    # random parameter search
    for i in range(0, 3):
        new_graph = tf.Graph()
        with new_graph.as_default():
            train_config, model_config = configuration_set()
            threshold = model_config.threshold
            data_object = read_data.LoadData(train_config=train_config, model_config=model_config)
            mutual_intensity_data = \
                Intensity.read_mutual_intensity_data(encoding=train_config.encoding,
                                                     mutual_intensity_path=train_config.mutual_intensity_path,
                                                     size=model_config.input_x_depth)
            key_node_list = build_model(model_config)
            train_metric_list, test_metric_list, roc = fine_tuning(train_config, key_node_list, data_object,
                                                                   train_config.save_path, mutual_intensity_data,
                                                                   threshold)
            pm.save_result(train_config.save_path, 'train_metric.csv', train_metric_list)
            pm.save_result(train_config.save_path, 'test_metric.csv', test_metric_list)
            pm.save_roc(train_config.save_path, 'roc.csv', roc)
            write_meta_data(train_config.meta_data, model_config.meta_data, train_config.save_path)


if __name__ == '__main__':
    # validation_test()
    main()
