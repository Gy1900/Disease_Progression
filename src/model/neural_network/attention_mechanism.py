# coding=utf-8
import configuration as config
import numpy as np
import tensorflow as tf


class HawkesBasedAttentionLayer(object):
    def __init__(self, model_configuration):
        """
        :param model_configuration contains
        x_depth:
        t_depth:
        name:
        init_map: should contain initializer with key mutual_intensity, combine
        time_decay_function: should be a list with length at l0000, each entry indicates the intensity at
        corresponding(the entry's index) day
        """
        self.__x_depth = model_configuration.input_x_depth
        self.__t_depth = model_configuration.input_t_depth
        self.__name = 'hawkes_based_attention'
        self.__init_map = model_configuration.init_map
        self.__time_decay_function = tf.convert_to_tensor(model_configuration.time_decay_function, dtype=tf.float64)
        self.__mutual_parameter = None  # with size [x_depth, 1]

        self.__init_argument_validation()
        self.__attention_parameter()

    def __call__(self, time_index, hidden_tensor, input_x, input_t, mutual_intensity):
        """
        get the mixed hidden state under the process of attention mechanism

        :param time_index: the time index, the first hidden state (not zero state) will be defined as time_index=0
        :param hidden_tensor: a hidden state tensor with size, [time_stamp, batch_size, hidden_state]
        :param input_x: tensor with size [max_time_stamp, batch_size, x_depth]
        :param input_t: tensor with size [max_time_stamp, batch_size, t_depth]
        :param mutual_intensity: a tensor with size [x_depth(event count), x_depth]
        :return: a mix hidden state at predefined time_index
        """
        self.__call_argument_validation(time_index, hidden_tensor, input_x, input_t, mutual_intensity)

        weight = self.__calc_weight(input_x, input_t, time_index, mutual_intensity)

        state = []
        with tf.name_scope('mix_' + str(time_index)):
            with tf.name_scope('mix'):
                for i in range(0, time_index + 1):
                    state.append(weight[i] * hidden_tensor[i])
            state = tf.convert_to_tensor(state, tf.float64)
            with tf.name_scope('average'):
                mix_state = tf.reduce_sum(state, axis=0)
        return mix_state

    def __calc_weight(self, input_x, input_t, time_index, mutual_intensity):
        """
        calculate all weights of previous event(including time_index itself), but do not consider the latter event
        :return: a normalized hidden state weight with size [time_index+1, batch_size, 1].
        """
        with tf.name_scope('data_unstack'):
            input_x_list = tf.unstack(input_x, axis=0)
            input_t_list = tf.unstack(input_t, axis=0)
            input_x_list = input_x_list[0: time_index + 1]
            input_t_list = input_t_list[0: time_index + 1]

        with tf.name_scope('unnormal_weight'):
            time_decay_function = self.__time_decay_function
            last_time = input_t_list[time_index][0]
            weight_list = []

            # calculate weight
            for i in range(0, time_index + 1):
                intensity_sum = 0
                for j in range(0, i + 1):
                    with tf.name_scope('time_calc'):
                        time_interval = tf.cast(last_time - input_t[j], dtype=tf.int64)
                        time_onehot = tf.one_hot(time_interval, time_decay_function.shape[0], dtype=tf.float64)
                    with tf.name_scope('decay_calc'):
                        time_decay = time_onehot * time_decay_function
                        time_decay = tf.reduce_sum(time_decay, axis=2)
                    with tf.name_scope('weight_calc'):
                        x_t_j = input_x_list[j]
                        intensity = tf.matmul(x_t_j, mutual_intensity)
                        intensity = tf.matmul(intensity, self.__mutual_parameter) * time_decay
                    intensity_sum += intensity
                weight_list.append(intensity_sum)
            unnormalized_weight = tf.convert_to_tensor(weight_list, dtype=tf.float64)

        with tf.name_scope('weight'):
            intensity_sum = tf.expand_dims(tf.reduce_sum(unnormalized_weight, axis=1), axis=2)
            weight = unnormalized_weight / intensity_sum

        return weight

    @staticmethod
    def __call_argument_validation(time_stamp, hidden_tensor, input_x, input_t, mutual_intensity):
        pass

    def __init_argument_validation(self):
        if not (self.__init_map.__contains__('mutual_intensity') and self.__init_map.__contains__('combine')):
            raise ValueError('init map should contain elements with name, mutual_intensity, combine')

    def __attention_parameter(self):
        size = self.__x_depth
        with tf.variable_scope('attention_para', reuse=tf.AUTO_REUSE):
            mutual = tf.get_variable(name='mutual', shape=[size, 1], dtype=tf.float64,
                                     initializer=self.__init_map['mutual_intensity'])
            self.__mutual_parameter = mutual


def unit_test():
    model_config = config.TestConfiguration.get_test_model_config()
    train_config = config.TestConfiguration.get_test_training_config()

    batch_size = train_config.batch_size
    placeholder_x = tf.placeholder('float64', [model_config.max_time_stamp, batch_size, model_config.input_x_depth])
    placeholder_t = tf.placeholder('float64', [model_config.max_time_stamp, batch_size, model_config.input_t_depth])
    hidden_tensor = tf.placeholder('float64', [model_config.max_time_stamp, batch_size, model_config.num_hidden])
    mutual_intensity = tf.convert_to_tensor(np.random.normal(0, 1, [model_config.input_x_depth,
                                                                    model_config.input_x_depth]))

    hawkes_attention = HawkesBasedAttentionLayer(model_config)
    for time_stamp in range(0, model_config.max_time_stamp):
        mix_state = hawkes_attention(time_stamp, hidden_tensor, placeholder_x, placeholder_t, mutual_intensity)
        print(mix_state)


if __name__ == "__main__":
    unit_test()