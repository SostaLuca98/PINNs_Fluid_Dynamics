#!/usr/bin/env python3

#%%
import os
cwd = os.path.abspath(os.getcwd())
os.chdir("../")
os.chdir("../")
import nisaba as ns
from nisaba.experimental.physics import tens_style as operator
import tensorflow as tf
import numpy as np

#############################################################################
#  u_x + v_y = 0                                           in \Omega = (-1, 1) x (-1, 1)
#  - (u_xx + u_yy) + p_x = 0                               in \Omega = (-1, 1) x (-1, 1)
#  - (v_xx + v_yy) + p_y = 0                               in \Omega = (-1, 1) x (-1, 1)
#  u = 20*x*y^3                                            on \partial\Omega
#  v = 5*x^4-5*y^4                                         on \partial\Omega
#
#  p_exact(x,y) = 60*x^2*y-20*y^3+const
#  u_exact(x,y) = 20*x*y^3
#  v_exact(x,y) = 5*x^4-5*y^4 
#############################################################################

# %% Options
# Fluid and Flow Setup
dim   = 2
a     = -1    # Lower extremum 
b     = +1     # Upper extremum

# Adimensionalization
Re = 1
L = 2

# %% Forcing and Solutions

forcing_x = lambda x: 0*x[:,0]
forcing_y = lambda x: 0*x[:,0] 

p_exact   = lambda x: (60*x[:,0]*x[:,0]*x[:,1]-20*x[:,1]*x[:,1]*x[:,1])
u_exact   = lambda x: 20*x[:,0]*x[:,1]*x[:,1]*x[:,1]
v_exact   = lambda x: 5*x[:,0]*x[:,0]*x[:,0]*x[:,0]-5*x[:,1]*x[:,1]*x[:,1]*x[:,1]
 
# %% Numerical options
num_PDE  = 50
num_BC   = 20 # points for each edge
num_hint = 5
num_test = 1000

# %% Inizialization

#  Set seeds for reproducibility
np.random.seed(1)
tf.random.set_seed(1)

model = tf.keras.Sequential([
    tf.keras.layers.Dense(20, input_shape=(2,), activation=tf.nn.tanh),
    tf.keras.layers.Dense(20, activation=tf.nn.tanh),
    tf.keras.layers.Dense(20, activation=tf.nn.tanh),
    tf.keras.layers.Dense(3)
])

x_PDE   = tf.random.uniform(shape = [num_PDE,  2], minval = [a, a],  maxval = [b, b], dtype = ns.config.get_dtype())
x_hint  = tf.random.uniform(shape = [num_hint, 2], minval = [a, a],  maxval = [b, b], dtype = ns.config.get_dtype())
x_BC_x0 = tf.random.uniform(shape = [num_BC,   2], minval = [a, a],  maxval = [a, b], dtype = ns.config.get_dtype())
x_BC_x1 = tf.random.uniform(shape = [num_BC,   2], minval = [b, a],  maxval = [b, b], dtype = ns.config.get_dtype())
x_BC_y0 = tf.random.uniform(shape = [num_BC,   2], minval = [a, a],  maxval = [b, a], dtype = ns.config.get_dtype())
x_BC_y1 = tf.random.uniform(shape = [num_BC,   2], minval = [a, b],  maxval = [b, b], dtype = ns.config.get_dtype())
x_test  = tf.random.uniform(shape = [num_test, 2], minval = [a, a],  maxval = [b, b], dtype = ns.config.get_dtype())

bound_cond = []
bound_cond.append(x_BC_x0)
bound_cond.append(x_BC_x1)
bound_cond.append(x_BC_y0)
bound_cond.append(x_BC_y1)
x_BCD = tf.concat(bound_cond, axis = 0)

u_max = np.max(np.abs(u_exact(x_BCD)))
v_max = np.max(np.abs(v_exact(x_BCD)))
p_max = np.max(np.abs(p_exact(x_BCD)))
vel_max = max([u_max, v_max])

# %% Random Noise

def generate_noise(x, factor = 0, sd = 1.0, mn = 0.0): 
    shape = x.shape[0]
    noise = tf.random.normal([shape], mean=mn, stddev=sd, dtype= ns.config.get_dtype())
    return noise * factor

use_noise = False
if use_noise:
    BCD_noise_x = generate_noise(x_BCD, factor = 1e-1)
    BCD_noise_y = generate_noise(x_BCD, factor = 1e-1)
else:
    BCD_noise_x = None
    BCD_noise_y = None

# %% Losses creation

def create_rhs(x, force, noise = None):
    samples = x.shape[0]
    if noise is None:
        noise = tf.zeros(shape = [samples], dtype = ns.config.get_dtype())
    if force is None:
        return tf.zeros(shape = [samples], dtype = ns.config.get_dtype()) + noise
    if type(force) == float:
        return tf.zeros(shape = [samples], dtype = ns.config.get_dtype()) + force + noise
    return force(x) + noise

# k is the coordinate of the vectorial equation
# j is the direction in which the derivative is computed

def PDE_MASS(x):
    with ns.GradientTape(persistent=True) as tape:
        tape.watch(x_PDE)
        u_vect = model(x_PDE)[:,0:2]*vel_max
        div = operator.divergence_vector(tape, u_vect, x_PDE, dim)
    return div

def PDE_MOM(x, k, force):
    with ns.GradientTape(persistent=True) as tape:
        tape.watch(x)
        
        u_vect = model(x)
        p = u_vect[:,2] * p_max
        u_eq = u_vect[:,k] * vel_max
        
        dp   = operator.gradient_scalar(tape, p, x)[:,k]
        lapl_eq = operator.laplacian_scalar(tape, u_eq, x, dim)
        
        rhs = create_rhs(x, force)
    return - (lapl_eq) + dp - rhs

def BC_D(x, k, g_bc = None, norm = 1, noise = None):     
    uk = model(x)[:,k] * norm
    rhs = create_rhs(x, g_bc, noise)
    return uk - rhs

def exact_value(x, k, sol = None, norm = 1):
    uk = model(x)[:,k] * norm
    rhs = create_rhs(x, sol)
    return uk - rhs

def exact_value_diff(x, k, sol = None, norm = 1):
    uk = model(x)[:,k] * norm
    uk_mean = tf.math.reduce_mean(uk)
    rhs = create_rhs(x, sol)
    return uk - rhs - uk_mean

# %% Training Losses definition
PDE_losses = [ns.LossMeanSquares('PDE_MASS', lambda: PDE_MASS(x_PDE), normalization = 1e4, weight = 1e0),
              ns.LossMeanSquares('PDE_MOMU', lambda: PDE_MOM(x_PDE, 0, forcing_x), normalization = 1e4, weight = 1e-2),
              ns.LossMeanSquares('PDE_MOMV', lambda: PDE_MOM(x_PDE, 1, forcing_y), normalization = 1e4, weight = 1e-2)]
BCD_losses = [ns.LossMeanSquares('BCD_u', lambda: BC_D(x_BCD, 0, u_exact, vel_max, BCD_noise_x), weight = 1e0),
              ns.LossMeanSquares('BCD_v', lambda: BC_D(x_BCD, 1, v_exact, vel_max, BCD_noise_y), weight = 1e0)]
EXC_Losses = [#ns.LossMeanSquares('exact_u', lambda: exact_value(x_hint, 0, u_exact, v_max), weight = 1e0),
              #ns.LossMeanSquares('exact_v', lambda: exact_value(x_hint, 1, v_exact, v_max), weight = 1e0),
              ns.LossMeanSquares('exact_p', lambda: exact_value(x_hint, 2, p_exact, p_max), weight = 1e0)]

losses = []
losses += PDE_losses 
losses += BCD_losses 
losses += EXC_Losses

# %% Test Losses definition
loss_test = [ns.LossMeanSquares('u_fit', lambda: exact_value(x_test, 0, u_exact, vel_max)),
             ns.LossMeanSquares('v_fit', lambda: exact_value(x_test, 1, v_exact, vel_max)),
             ns.LossMeanSquares('p_fit', lambda: exact_value(x_test, 2, p_exact, p_max))]

# %% Training
pb = ns.OptimizationProblem(model.variables, losses, loss_test)

ns.minimize(pb, 'keras', tf.keras.optimizers.Adam(learning_rate=1e-2), num_epochs = 100)
ns.minimize(pb, 'scipy', 'L-BFGS-B', num_epochs = 1000)

# %% Saving Loss History

problem_name = "Colliding_Flows"
history_file = os.path.join(cwd, "Images\\{}_history_loss.json".format(problem_name))
pb.save_history(history_file)
ns.utils.plot_history(history_file)
history = ns.utils.load_json(history_file)

# %% Post-processing

p_test   = p_exact(x_test)[:, None]
u_test   = u_exact(x_test)[:, None]
v_test   = v_exact(x_test)[:, None]

import matplotlib.pyplot as plt

fig_1 = plt.figure(2)
ax_1 = fig_1.add_subplot(projection='3d')
ax_1.scatter(x_test[:,0], x_test[:,1], u_test, label = 'exact solution')
ax_1.scatter(x_test[:,0], x_test[:,1], model(x_test)[:,0].numpy() * vel_max, label = 'numerical solution')
ax_1.legend()
ax_1.set_xlabel('x')
ax_1.set_ylabel('y')
ax_1.set_zlabel('velocity u')
image_file = os.path.join(cwd, "Images\\{}_velocity_u.png".format(problem_name))
plt.savefig(image_file)

fig_2 = plt.figure(3)
ax_2 = fig_2.add_subplot(projection='3d')
ax_2.scatter(x_test[:,0], x_test[:,1], v_test, label = 'exact solution')
ax_2.scatter(x_test[:,0], x_test[:,1], model(x_test)[:,1].numpy() * vel_max, label = 'numerical solution')
ax_2.legend()
ax_2.set_xlabel('x')
ax_2.set_ylabel('y')
ax_2.set_zlabel('velocity v')
image_file = os.path.join(cwd, "Images\\{}_velocity_v.png".format(problem_name))
plt.savefig(image_file)

fig_3 = plt.figure(4)
p_output = model(x_test)[:,2].numpy()* p_max
p_zero   = p_output - np.mean(p_output) 
ax_3 = fig_3.add_subplot(projection='3d')
ax_3.scatter(x_test[:,0], x_test[:,1], p_test, label = 'exact solution')
ax_3.scatter(x_test[:,0], x_test[:,1], p_zero, label = 'numerical solution')
ax_3.legend()
ax_3.set_xlabel('x')
ax_3.set_ylabel('y')
ax_3.set_zlabel('pressure')
image_file = os.path.join(cwd, "Images\\{}_pressure.png".format(problem_name))
plt.savefig(image_file)

plt.show(block = False)
print("Pressure mean ->",np.mean(p_output))