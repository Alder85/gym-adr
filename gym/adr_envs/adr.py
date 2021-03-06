import numpy as np 
import math
from enum import IntEnum

"""
Automatic Domain Randomization in Python

I'm open to suggestion/refactors should this implementation be insufficient

Currently supports generic and some custom randomizers from the paper
Creating new custom randomizers should be somewhat trivial

(Questionable) Design Decisions:
 - No generic sample() function, must explicitly choose episode vs step sample
 - Step sample is left un-implemented in some generic randomizers (I need to think more about the effects of this)
 - ADRUniform is the only ADRDist directly dependent on ADRParam, and thus everything must have this has it's base distribution
 - ADRDist is a parent class that all distributions must extend, but that is the maximum intended extent of the hierarchy currently.
   The classes have a lot of specific members and I want to keep the implementation as close to the data as possible (short of a completely procedural implementation)
 - In the paper, all custom randomizers are based off of a Uniform Distribution. I provide the option to use a generic ADRDist should this be desired.
   Potential uses of this are anyone's guess.
 - g_func is from the paper, I don't have a large intuition for it's usefulness currently

(Questionable) Notation Decisions:
lam/lambda -> A distribution, most commonly uniform
x -> Refers to the output of some distributions, to differentiate between inputs (which are x_0 or lam)
x_0 -> usually an initial value or center of a distribution
g -> g_func
N -> normal distribution
U -> uniform distribution
a -> alpha

TODO:
 - Standardize documentation somehow, probably in a README
 - LaTeX for documentation
 - Improve tests
"""

class Bound(IntEnum):
    LOWER, UPPER = range(2)

class Direction(IntEnum):
    EXPAND, SHRINK = range(2)

"""
Defined in Appendix B of ADR paper
"""
def g_func(x):
    return np.exp(x - 1)

class ADRParam():
    """
    Automatic Domain Randomization single parameter
    Contains a value, min-max bounds, a delta, a performance queue, and a sampling weight
    """
    def __init__(self, value, val_bound=[-math.inf, math.inf], delta=0.02, pq_size=240, boundary_sample_weight=1, name=""):
        self.value = value 
        self.val_bound = val_bound 
        self.delta = delta
        self.pq_size = pq_size 
        self.pq = [] 
        self.boundary_sample_weight = boundary_sample_weight 
        self.boundary_sample_flag = False 
        self.name = name 
    
    @staticmethod
    def fixed_boundary(val):
        """
        Creates an ADRParam that is fixed. It will not be boundary sampled or updated.
        """
        return ADRParam(
            value = val,
            delta = 0,
            pq_size = 0,
            boundary_sample_weight = 0
        )
    """
    Takes a performance value, updates it pq is full based on average performance over pq_size updates
    """
    def update(self, p_val, p_thresh):
        self.pq.append(p_val)
        if len(self.pq) >= self.pq_size:
            pq_avg = np.mean(self.pq)
            self.pq = [] 
            if pq_avg < p_thresh[Bound.LOWER]:
                self.value -= self.delta 
            elif pq_avg > p_thresh[Bound.UPPER]:
                self.value += self.delta
            
            self.value = np.clip(self.value, self.val_bound[Bound.LOWER], self.val_bound[Bound.UPPER])
    
    def get_boundary_sample_flag(self):
        return self.boundary_sample_flag

    def set_boundary_sample_flag(self, flag_val):
        self.boundary_sample_flag = flag_val
    
    def get_boundary_sample_weight(self):
        return self.boundary_sample_weight

    """
    Returns value
    """
    def get_value(self):
        return self.value 

class ADRDist():
    """
    ADRDist is provided as a base class for all ADR distributions
    All distributions share at least a collection of parameters and the storing of a last sample

    Many distributions are constructed using other distributions, so this class provides the ability to check types
    Most commonly the ADRDist parameter passed into a complicated distribution will be of type ADRUniform,
    however I don't limit it to that should the user decide to stack highly complicated distributions.
    """
    def __init__(self):
        self.last_sample = None
        self.parameters = None
        self.name = ""

    # self.parameters should be list of ADRParam objects
    def get_parameters(self):
        return self.parameters

    # Samples used to construct a single instance of the environment, i.e. a single lambda_i in env(lambda) ~ P(phi)
    def episode_sample(self): 
        raise NotImplementedError

    # Samples used in a single step of the environment, not always needed
    def step_sample(self):
        raise NotImplementedError

    # All distributions should store the most recent sample in case they are used by another distribution that works across both episodes and steps
    def get_last_sample(self):
        return self.last_sample

class ADRUniform(ADRDist):
    """
    Uniform Distribution off of 2 parameters
    i.e. x = U(phi^L, phi^H)
    """
    def __init__(self, phi_l: ADRParam, phi_h: ADRParam, name=""):
        super().__init__()
        self.phi_l = phi_l 
        self.phi_h = phi_h
        self.parameters = [self.phi_l, self.phi_h]
        self.name = name 
        self.update_boundary_names()
    
    def update_boundary_names(self):
        self.phi_l.name = self.name + "_l"
        self.phi_h.name = self.name + "_r"

    def episode_sample(self):
        for param in self.parameters:
            if param.get_boundary_sample_flag():
                param.set_boundary_sample_flag(False)
                self.last_sample = param.get_value()
        self.last_sample = np.random.uniform(self.phi_l.get_value(), self.phi_h.get_value())
        return self.last_sample #return for convienience
    
    @staticmethod
    def from_bounds_only(low_value, high_value, name=""):
        """
        Constructs an ADRUniform based off of two values.
        Picks a midpoint between them as a point they cannot cross,
        and provides no minimum or maximum for either bound to reach.
        this probably shouldn't be used that often.
        """
        midpoint = (low_value + high_value) / 2
        l = ADRParam(
            value = low_value,
            val_bound = [-math.inf, midpoint]
        )
        r = ADRParam(
            value = high_value,
            val_bound = [midpoint, math.inf]
        )
        return ADRUniform(l, r, name)
    
    @staticmethod 
    def centered_around(low, start, high, delta=0.02, pq_size=240, boundary_sample_weight=1, name=""):
        """
        Constructs an ADRUniform that starts at "start" and can expand to [low, high], without allowing the bounds to cross the center point.
        Useful for generating values where the default is the "easiest" to generalize for, and expansions in any direction increase difficulty
        """
        l = ADRParam(
            value = start,
            val_bound = [low, start],
            delta = -delta,
            pq_size = pq_size,
            boundary_sample_weight = boundary_sample_weight
        )
        r = ADRParam(
            value = start,
            val_bound = [start, high],
            delta = delta,
            pq_size = pq_size,
            boundary_sample_weight = boundary_sample_weight
        )
        return ADRUniform(l, r, name)
    
    @staticmethod 
    def fixed_value(value, name=""):
        """
        Constructs an ADRUniform that will always return a set value.
        Useful for cases where a parameter is normally randomized, but needs to
        be fixed for a test case.
        """
        l = ADRParam.fixed_boundary(value)
        r = ADRParam.fixed_boundary(value)
        return ADRUniform(l, r, name)

class ADRAdditiveGaussian(ADRDist):
    """
    Additive Gaussian Distribution
    i.e. x = x_0 + |N| for N ~ N(g(a*lam_i), g(|a*lam_j|)^2)
    """
    def __init__(self, x_0, lam_i: ADRDist, lam_j: ADRDist, alpha=0.01):
        super().__init__()
        self.x_0 = x_0
        self.lam_i = lam_i 
        self.lam_j = lam_j 
        self.alpha
        self.parameters = [self.lam_i.get_parameters() + self.lam_j.get_parameters]
    
    def episode_sample(self):
        self.last_sample = self.x_0 + np.abs(
            np.random.normal(
                g_func(
                    self.alpha * self.lam_i.episode_sample()
                    ),
                g_func(
                    np.abs(
                        self.alpha * self.lam_j.episode_sample()
                    )
                )
            )
        )
        return self.last_sample

class ADRUnbiasedAdditiveGaussian(ADRDist):
    """
    Unbiassed Additive Gaussian Distribution
    i.e. x = x_0 + N for N ~ N(0, g(|a*lam_i|)^2)
    """
    def __init__(self, x_0, lam_i: ADRDist, alpha=0.01):
        super().__init__()
        self.x_0 = x_0 
        self.lam_i = lam_i 
        self.alpha = alpha 
        self.parameters = self.lam_i.get_parameters() 

    def episode_sample(self):
        self.last_sample = self.x_0 + np.random.normal(
            0,
            g_func(
                np.abs(
                    self.alpha * self.lam_i.episode_sample()
                )
            )
        )
        return self.last_sample

class ADRMultiplicative(ADRDist):
    """
    Multiplicative Distribution
    i.e. x_0*e^N for N ~ N(a*lam_i, |a*lam_j|^2)
    """
    def __init__(self, x_0, lam_i: ADRDist, lam_j: ADRDist, alpha=0.01):
        super().__init__()
        self.x_0 = x_0 
        self.lam_i = lam_i 
        self.lam_j = lam_j 
        self.alpha = alpha 
        self.parameters = self.lam_i.get_parameters() + self.lam_j.get_parameters  
    
    def episode_sample(self):
        self.last_sample = self.x_0 * np.exp(
            np.random.normal(
                self.alpha * self.lam_i.episode_sample(),
                np.abs(
                    self.alpha * self.lam_j.episode_sample()
                )
            )
        )
        return self.last_sample

class ADRActionNoise(ADRDist):
    """
    Action Noise where n_0 and n_1 are episode-sampled, and n_2 is step-sampled
    a = a_0*n_0 + n_1 + n_2
    n_0 ~ N(1, g(|lam_i|)^2)
    n_1 ~ N(0, g(|lam_j|)^2)
    n_2 ~ N(a*lam_i,|a*lam_j|^2)
    """
    def __init__(self, a_0, lam_i: ADRDist, lam_j: ADRDist, lam_k: ADRDist):
        super().__init__()
        self.a_0 = a_0 
        self.lam_i = lam_i 
        self.lam_j = lam_j 
        self.lam_k = lam_k 
        self.parameters = self.lam_i.get_parameters() + self.lam_j.get_parameters + self.lam_k.get_parameters

    def episode_sample(self):
        self.lam_i.episode_sample() 
        self.lam_j.episode_sample()
        return self.step_sample()
    
    def step_sample(self):
        self.last_sample = a_0 * np.random.normal(
            1,
            g_func(
                np.abs(
                    self.lam_i.get_last_sample()
                )
            )
        ) 
        + np.random.normal(
            0,
            g_func(
                np.abs(
                    self.lam_j.get_last_sample()
                )
            )
        )
        + np.random.normal(
            0,
            g_func(
                np.abs(
                    self.lam_k.episode_sample()
                )
            )
        )
        return self.last_sample


class ADR():

    def __init__(self, distributions, p_thresh=[0, 10]):
        super().__init__()
        self.distribution_dict = ADR.construct_dict(distributions)
        self.p_thresh = p_thresh 
        self.parameters = []
        self.sample_idx = None 
        self.distributions = distributions
        for dist in self.distributions:
            self.parameters += dist.get_parameters()
        
        self.do_boundary_sample = True 

    @staticmethod
    def construct_dict(distributions):
        ph_val = 0
        distribution_dict = {}
        for dist in distributions:
            if dist.name in distribution_dict:
                dist.name = "dist_{}".format(ph_val)
                dist.update_boundary_names()
            distribution_dict[dist.name] = dist
        
        return distribution_dict


    def episode_sample(self):
        lam = [] 
        for dist in self.distributions:
            lam.append(dist.episode_sample())
        return lam 
    
    def boundary_sample(self):
        if self.do_boundary_sample: #this is horrible TODO fix this trash
            sample_weights = [param.get_boundary_sample_weight() for param in self.parameters]
            weights_norm = sample_weights / np.sum(sample_weights)
            self.sample_idx = np.random.choice(len(self.parameters), p=weights_norm)
            self.parameters[self.sample_idx].set_boundary_sample_flag(True)

            return self.episode_sample(), self.sample_idx 
        else:
            self.sample_idx = 0
            return self.episode_sample(), self.sample_idx 
    
    def update(self, performance, param_idx=None):
        if param_idx is None:
            param_idx = self.sample_idx 
        self.parameters[param_idx].update(performance, self.p_thresh)
    
    #this is really a horrible way to do things
    #sit down and formulate this on a whiteboard
    #like it kinda works right now but like no
    def total_distribution_width(self): 
        total = 0
        for dist in self.distributions:
            total += (dist.phi_h.value - dist.phi_l.value)
        
        return total 

