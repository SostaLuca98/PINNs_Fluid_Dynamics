# %% Setup Options --- Import Libraries

# Main Libraries
import os
import numpy as np
import tensorflow as tf

# Setting Names and Working Directory 
problem_name = "Cavity_Steady"
cwd = os.path.abspath(os.getcwd())
nisaba_wd = "../../../nisaba"

# Import Nisaba Library
os.chdir(nisaba_wd)
import nisaba as ns
os.chdir(cwd)

# %% Setup Options --- Saving Options

save_results = True

default_name    = "Test_Case_#"
default_folder  = "Last_Training" 
recap_file_name = "Test_Options.txt"

test_cases = [x for x in os.listdir() if x.startswith(default_name)]
naming_idx = 1 if not test_cases else (max([int(x[len(default_name):]) for x in test_cases])+1)
saved_test_folder = f"{default_name}{naming_idx:03d}"

saving_folder  = saved_test_folder if save_results else default_folder  
if save_results: os.mkdir(saving_folder)
else: 
    if default_folder not in os.listdir(): os.mkdir(default_folder)

# %% Setup Options --- Setting Simulation Options

options_file_name = "simulation_options.txt"
options_file_path = os.path.join(cwd,options_file_name)
with open(options_file_path) as options_file:
    simulation_options = options_file.readlines()[0:-1:2]

epochs = int(simulation_options[1])
noise_factor_col = float(simulation_options[2])
noise_factor_bnd = float(simulation_options[3])

n_pts = {}
n_pts["PDE"]  = int(simulation_options[4])
n_pts["BC"]   = int(simulation_options[5])
n_pts["IC"]   = int(simulation_options[6])
n_pts["Vel"]  = int(simulation_options[7])
n_pts["Pres"] = int(simulation_options[8])
n_pts["Test"] = int(simulation_options[9])

use_pdelosses = True if n_pts["PDE"]  else False
use_boundaryc = True if n_pts["BC"]   else False
use_initialco = False
coll_velocity = True if n_pts["Vel"]  else False
coll_pressure = True if n_pts["Pres"] else False

# %% Setup Options --- Setting Physical Parameters

dim = 2    # set 2D or 3D for operators

# Domain Dimensions 
Le_x  = 0    # Lower x extremum
Ue_x  = 1    # Upper x extremum
Le_y  = 0    # Lower y extremum
Ue_y  = 1    # Upper y extremum

# Physical Forces
bnd_val = [{},{}]
bnd_val[0]["BOT"] = 0
bnd_val[0] ["DX"] = 0
bnd_val[0]["TOP"] = 500
bnd_val[0] ["SX"] = 0
bnd_val[1]["BOT"] = 0
bnd_val[1] ["DX"] = 0
bnd_val[1]["TOP"] = 0
bnd_val[1] ["SX"] = 0

# %% Data Creation --- Building the Grid

n1, n2 = 100, 100 
n = (n1+1)*(n2+1)

# Uniform Mesh
uniform_mesh = True
x_vec = np.linspace(Le_x, Ue_x, n1+1) if uniform_mesh else np.random.uniform(Le_x, Ue_x, n1+1)
y_vec = np.linspace(Le_y, Ue_y, n2+1) if uniform_mesh else np.random.uniform(Le_y, Ue_y, n2+1)

dom_grid = tf.convert_to_tensor([(i,j) for j in y_vec for i in x_vec])

key_subset = ("PDE", "Vel", "Pres", "Test")
val_subset = np.split(np.random.permutation(np.array([i for i in range(dom_grid.shape[0])])), 
                      np.cumsum([n_pts[x] for x in key_subset]))[:-1]
idx_set = {k : v for (k,v) in zip(key_subset,val_subset)}

# %% Data Creation --- Exact Solution (Import Data or Analitical)

import h5py
folder_h5 = "../../DataGeneration/data/SteadyCase"
data_h5 = lambda : h5py.File(f'{folder_h5}/navier-stokes_cavity_steady.h5', "r")['VisualisationVector']
uvel_h5 = lambda : data_h5()["0"][:,0]
vvel_h5 = lambda : data_h5()["0"][:,1]
pres_h5 = lambda : data_h5()["1"][()] - np.mean(data_h5()["1"][()])

u_ex = tf.convert_to_tensor(uvel_h5())
v_ex = tf.convert_to_tensor(vvel_h5())
p_ex = tf.convert_to_tensor(pres_h5())

# %% Data Creation --- Data Normalization 

spread = lambda vec: np.max(vec) - np.min(vec)
norm_vel = max([spread(u_ex), spread(v_ex)])
norm_pre = spread(p_ex)

u_ex_norm = u_ex / norm_vel
v_ex_norm = v_ex / norm_vel
p_ex_norm = p_ex / norm_pre
sol_norm  = [u_ex_norm , v_ex_norm, p_ex_norm]

# %% Data Creation --- Boundary and Initial Conditions

bnd_pts = {}
boundary_sampling = lambda minval, maxval: tf.random.uniform(shape = [n_pts["BC"], dim], minval = minval, maxval = maxval)

bnd_pts["BOT"] = boundary_sampling([Le_x, Le_y], [Ue_x, Le_y])
bnd_pts["DX"]  = boundary_sampling([Ue_x, Le_y], [Ue_x, Ue_y])
bnd_pts["TOP"] = boundary_sampling([Le_x, Ue_y], [Ue_x, Ue_y])
bnd_pts["SX"]  = boundary_sampling([Le_x, Le_y], [Le_x, Ue_y])

zero_base = tf.zeros(shape = [n_pts["BC"]], dtype = np.double)

for key, value in bnd_val[0].items():
    bnd_val[0][key] = zero_base + value/norm_vel if type(value) == float or type(value) == int else zero_base + value(bnd_pts[key])/norm_vel
for key, value in bnd_val[1].items():
    bnd_val[1][key] = zero_base + value/norm_vel if type(value) == float or type(value) == int else zero_base + value(bnd_pts[key])/norm_vel

# %% Data Creation --- Noise Management

def generate_noise(n_pts, factor = 0, sd = 1.0, mn = 0.0):
    noise = tf.random.normal([n_pts], mean=mn, stddev=sd, dtype= np.double)
    return noise * factor

for key, _ in bnd_val[0].items():
    bnd_val[0][key] += generate_noise(n_pts["BC"], noise_factor_bnd)
    bnd_val[1][key] += generate_noise(n_pts["BC"], noise_factor_bnd)


u_ex_noise = tf.gather(u_ex_norm,idx_set["Vel"]) + generate_noise(n_pts[ "Vel"], noise_factor_col)
v_ex_noise = tf.gather(v_ex_norm,idx_set["Vel"]) + generate_noise(n_pts[ "Vel"], noise_factor_col)
p_ex_noise = tf.gather(p_ex_norm,idx_set["Vel"]) + generate_noise(n_pts["Pres"], noise_factor_col)
sol_noise  = [u_ex_noise , v_ex_noise, p_ex_noise]

# %% Loss Building --- Differential Losses

gradient = ns.experimental.physics.tens_style.gradient_scalar

def PDE_MASS():
    x = tf.gather(dom_grid, idx_set["PDE"])
    with ns.GradientTape(persistent=True) as tape:
        tape.watch(x)
        u_vect = model(x)[:,0:2]
        du_x = gradient(tape, u_vect[:,0], x)[:,0]
        dv_y = gradient(tape, u_vect[:,1], x)[:,1]
    return du_x + dv_y

def PDE_MOM(k):
    x = tf.gather(dom_grid, idx_set["PDE"])
    with ns.GradientTape(persistent=True) as tape:
        tape.watch(x)
        
        u_vect = model(x)
        p    = u_vect[:,2] * norm_pre
        u_eq = u_vect[:,k] * norm_vel

        dp    = gradient(tape, p, x)[:,k]
        du_x  = gradient(tape, u_eq, x)[:,0]
        du_y  = gradient(tape, u_eq, x)[:,1]
        du_xx = gradient(tape, du_x, x)[:,0]
        du_yy = gradient(tape, du_y, x)[:,1]

        conv1 = tf.math.multiply(norm_vel * u_vect[:,0], du_x)
        conv2 = tf.math.multiply(norm_vel * u_vect[:,1], du_y)
        unnormed_lhs = du_xx - du_yy + dp + conv1 + conv2
        norm_const = 1/max(norm_pre,norm_vel)

    return unnormed_lhs*norm_const

# %% Loss Building --- Dirichlet Style Losses

def dir_loss(points, component, rhs):
    uk = model(points)[:,component]
    return uk - rhs

BC_D = lambda edge, component:   dir_loss(bnd_pts[edge], component, bnd_val[component][edge])
IN_C = lambda component:         dir_loss(bnd_pts["IC"], component, tf.zeros(shape = [n_pts["IC"]], dtype = np.double))
col_velocity = lambda component: dir_loss(tf.gather(dom_grid,idx_set["Vel" ]), component, sol_noise[component])
col_pressure = lambda:           dir_loss(tf.gather(dom_grid,idx_set["Pres"]), 2, sol_noise[2])
exact_value  = lambda component: dir_loss(tf.gather(dom_grid,idx_set["Test"]), component, tf.gather(sol_norm[component],idx_set["Test"]))

# %% Model's Setup --- Model Creation

model = tf.keras.Sequential([
    tf.keras.layers.Dense(32, input_shape=(dim,), activation=tf.nn.tanh),
    tf.keras.layers.Dense(32, activation=tf.nn.tanh),
    tf.keras.layers.Dense(32, activation=tf.nn.tanh),
    tf.keras.layers.Dense(3)
])

LMS = ns.LossMeanSquares

PDE_losses = [LMS('PDE_MASS', lambda: PDE_MASS(), weight = 1e1),
              LMS('PDE_MOMU', lambda: PDE_MOM(0), weight = 1e0),
              LMS('PDE_MOMV', lambda: PDE_MOM(1), weight = 1e0)]
BCD_losses = [LMS('BCD_u_x0', lambda: BC_D( "SX", 0), weight = 1e0),
              LMS('BCD_v_x0', lambda: BC_D( "SX", 1), weight = 1e0),
              LMS('BCD_u_x1', lambda: BC_D( "DX", 0), weight = 1e0),
              LMS('BCD_v_x1', lambda: BC_D( "DX", 1), weight = 1e0),
              LMS('BCD_u_y0', lambda: BC_D("BOT", 0), weight = 1e0),
              LMS('BCD_v_y0', lambda: BC_D("BOT", 1), weight = 1e0),
              LMS('BCD_u_y1', lambda: BC_D("TOP", 0), weight = 1e0),
              LMS('BCD_v_y1', lambda: BC_D("TOP", 1), weight = 1e0),]
COL_V_Loss = [LMS('COL_u', lambda: col_velocity(0), weight = 1e0),
              LMS('COL_v', lambda: col_velocity(1), weight = 1e0)]
COL_P_Loss = [LMS('COL_p', lambda: col_pressure(), weight = 1e0)]

losses = []
if use_pdelosses: losses += PDE_losses
if use_boundaryc: losses += BCD_losses
if coll_velocity: losses += COL_V_Loss
if coll_pressure: losses += COL_P_Loss

loss_test = [LMS('u_fit', lambda: exact_value(0)),
             LMS('v_fit', lambda: exact_value(1)),
             LMS('p_fit', lambda: exact_value(2))]

# %% Model's Setup --- Training Section

loss_image_file = os.path.join(cwd, "{}//Loss_Trend.png".format(saving_folder))
history_file    = os.path.join(cwd, "{}//History_Loss.json".format(saving_folder))

pb = ns.OptimizationProblem(model.variables, losses, loss_test, callbacks=[])
pb.callbacks.append(ns.utils.HistoryPlotCallback(frequency=100, gui=False,
                                                 filename=loss_image_file,
                                                 filename_history=history_file))
ns.minimize(pb, 'keras', tf.keras.optimizers.Adam(learning_rate=1e-2), num_epochs = 100)
ns.minimize(pb, 'scipy', 'BFGS', num_epochs = epochs)

# %% Image Process --- Solutions on Regular Grid

import pandas as pd

# Regular Grid
grid_x, grid_y = np.meshgrid(np.linspace(Le_x, Ue_x , 100), np.linspace(Le_y, Ue_y, 100))

# Numerical Solutions
regular_mesh_file = r'../../DataGeneration/data/SteadyCase/navier-stokes_cavity_steady_r.csv'
dfr = pd.read_csv (regular_mesh_file)

p_temp = pd.DataFrame(dfr, columns = ['p']).to_numpy().reshape(grid_x.shape)
p_ex_list = p_temp-np.mean(p_temp)
u_ex_list = pd.DataFrame(dfr, columns = ['ux']).to_numpy().reshape(grid_x.shape)
v_ex_list = pd.DataFrame(dfr, columns = ['uy']).to_numpy().reshape(grid_x.shape)

# %% Image Process --- PINN Solutions 

grid_x_flatten = np.reshape(grid_x, (-1,))
grid_y_flatten = np.reshape(grid_y, (-1,)) 

u_list, v_list, p_list = [], [], []

grid = tf.stack([grid_x_flatten, grid_y_flatten], axis = -1)
u_list = model(grid)[:,0].numpy().reshape(grid_x.shape) * norm_vel
v_list = model(grid)[:,1].numpy().reshape(grid_x.shape) * norm_vel
p_list = model(grid)[:,2].numpy().reshape(grid_x.shape) * norm_pre

# %% Image Process --- Contour Levels

def find_lims(exact_sol, pinn_sol, take_max):
    pfunc = max if take_max else min
    nfunc = np.max if take_max else np.min
    levels = pfunc(nfunc(exact_sol),nfunc(pinn_sol))
    return levels

lev_u_min, lev_u_max = (find_lims(u_ex_list, u_list, False), find_lims(u_ex_list, u_list, True))
lev_v_min, lev_v_max = (find_lims(v_ex_list, v_list, False), find_lims(v_ex_list, v_list, True))
lev_p_min, lev_p_max = (find_lims(p_ex_list, p_list, False), find_lims(p_ex_list, p_list, True))

def approx_scale(x, up):
    factor = np.floor(np.log10(abs(x)))-1
    if up: x =  np.ceil(x/(np.power(10,factor))/5)
    else : x = np.floor(x/(np.power(10,factor))/5)
    return x*5*np.power(10,factor)

num_levels = 11 
level_u = np.linspace(approx_scale(lev_u_min, False), approx_scale(lev_u_max, True), num_levels)
level_v = np.linspace(approx_scale(lev_v_min, False), approx_scale(lev_v_max, True), num_levels)
level_p = np.linspace(approx_scale(lev_p_min, False), approx_scale(lev_p_max, True), num_levels)

# %% Image Process --- Countour Plots

import matplotlib.pyplot as plt

def plot_subfig(fig, ax, function, levels, title):
    ax.title.set_text(title)
    cs = ax.contourf(grid_x, grid_y, function, levels = levels)
    fig.colorbar(cs, ax=ax)


graph_title = "Solutions of the {} problem".format(problem_name)
    
# Figure Creation
fig, ((ax1, ax2), (ax3, ax4), (ax5, ax6)) = plt.subplots(3, 2, figsize=(12,8))
fig.suptitle(graph_title , fontsize=18, y = 0.97, x = 0.50)
plt.subplots_adjust(top = 1.4, right = 1)
    
plot_subfig(fig, ax1, u_ex_list, level_u, 'Numerical u-velocity')
plot_subfig(fig, ax2, u_list, level_u, 'PINNS u-velocity')
plot_subfig(fig, ax3, v_ex_list, level_v, 'Numerical v-velocity')
plot_subfig(fig, ax4, v_list, level_v, 'PINNS v-velocity')
plot_subfig(fig, ax5, p_ex_list, level_p, 'Numerical Pressure')
plot_subfig(fig, ax6, p_list, level_p, 'PINNS Pressure')
    
plt.tight_layout()
saving_file = os.path.join(cwd, "{}//Graphic.jpg".format(saving_folder))
plt.savefig(saving_file)
    
# %% Final Recap

recap_info = []
recap_info.append("Problem Name    -> {}".format(problem_name))
recap_info.append("Training Epochs -> {} epochs".format(epochs))
recap_info.append("Pyhsical PDE Losses  -> {} points".format(n_pts["PDE"]))
recap_info.append("Boundary Conditions  -> {} points".format(n_pts["BC"]))
recap_info.append("Initial  Conditions  -> {} points".format(n_pts["IC"]))
recap_info.append("Collocation Velocity -> {} points".format(n_pts["Vel"]  if coll_velocity else 0))
recap_info.append("Collocation Pressure -> {} points".format(n_pts["Pres"] if coll_pressure else 0))
recap_info.append("Noise on Boundary -> {} times a gaussian N(0,1)".format(noise_factor_bnd))
recap_info.append("Noise on Domain   -> {} times a gaussian N(0,1)".format(noise_factor_col))

recap_file_path = os.path.join(os.path.join(cwd, saving_folder),recap_file_name)
recap_file = open(recap_file_path, "w")                                                                          
print("\nSIMULATION OPTIONS RECAP...")
for row_string in recap_info:
    print("\t",row_string)
    recap_file.write(row_string+"\n")
recap_file.close()