import numpy as np
import pandas as pd
from gpiozero import PWMLED
import time
from datetime import datetime, timedelta

# Initialize PWM-capable pins for RGB LEDs
red_led = PWMLED(12)    # PWM0
green_led = PWMLED(19)  # PWM1
blue_led = PWMLED(13)   # PWM1

# Load CIE data from CSV file
cie_data = pd.read_csv('CIE_xyz_1931_2deg.csv', header=None)

# Extract wavelength and color matching functions data
wavelengths = cie_data.iloc[:, 0].values
x_bar = cie_data.iloc[:, 1].values
y_bar = cie_data.iloc[:, 2].values
z_bar = cie_data.iloc[:, 3].values

# Standard RGB transformation matrix from XYZ (sRGB color space)
xyz_to_rgb_matrix = np.array([
    [3.2406, -1.5372, -0.4986],
    [-0.9689, 1.8758, 0.0415],
    [0.0557, -0.2040, 1.0570]
])

class ColorTemperatureConverter:
    def __init__(self, cct):
        self.cct = cct

    def planck_law(self, wavelength):
        h = 6.62607015e-34
        c = 2.99792458e8
        k = 1.380649e-23
        l = wavelength * 1e-9
        return (2 * h * c ** 2) / (l ** 5) * (1 / (np.exp(h * c / (l * k * self.cct)) - 1))

    def cct_to_xyz(self):
        spectral_radiance = self.planck_law(wavelengths)
        X = np.trapz(spectral_radiance * x_bar, wavelengths)
        Y = np.trapz(spectral_radiance * y_bar, wavelengths)
        Z = np.trapz(spectral_radiance * z_bar, wavelengths)
        
        XYZ = np.array([X, Y, Z])
        XYZ /= np.max(XYZ)
        return XYZ

    def xyz_to_rgb(self, xyz):
        rgb = np.dot(xyz_to_rgb_matrix, xyz)
        rgb = np.clip(rgb, 0, 1)
        rgb = (rgb * 255).astype(int)
        return rgb

    def get_rgb(self):
        xyz = self.cct_to_xyz()
        return self.xyz_to_rgb(xyz)

    def visualize_rgb_led(self):
        rgb = self.get_rgb()
        r, g, b = rgb
        red_led.value = r / 255
        green_led.value = g / 255
        blue_led.value = b / 255
        print(f"CCT: {self.cct}K -> RGB: {rgb}")

def load_lookup_table(filename):
    df = pd.read_csv(filename)
    df['Time'] = pd.to_datetime(df['Time'], format='%I:%M %p').dt.time
    # Sort the dataframe by time to ensure correct interpolation
    df = df.sort_values('Time')
    return df

def interpolate_color_temperature(lookup_table, current_time):
    current_time = current_time.time()
    
    # If the current time is exactly in the lookup table, return that value
    if current_time in lookup_table['Time'].values:
        return lookup_table[lookup_table['Time'] == current_time]['Color Temperature (K)'].values[0]
    
    # Find the two closest times in the lookup table
    lower_time = lookup_table[lookup_table['Time'] <= current_time]['Time'].max()
    upper_time = lookup_table[lookup_table['Time'] > current_time]['Time'].min()
    
    # Handle the case where current_time is after the last or before the first entry
    if pd.isnull(lower_time):
        lower_time = lookup_table['Time'].max()
        upper_time = lookup_table['Time'].min()
    elif pd.isnull(upper_time):
        upper_time = lookup_table['Time'].min()
        lower_time = lookup_table['Time'].max()
    
    lower_temp = lookup_table[lookup_table['Time'] == lower_time]['Color Temperature (K)'].values[0]
    upper_temp = lookup_table[lookup_table['Time'] == upper_time]['Color Temperature (K)'].values[0]
    
    # Convert times to total seconds for interpolation
    current_seconds = current_time.hour * 3600 + current_time.minute * 60 + current_time.second
    lower_seconds = lower_time.hour * 3600 + lower_time.minute * 60 + lower_time.second
    upper_seconds = upper_time.hour * 3600 + upper_time.minute * 60 + upper_time.second
    
    # Handle midnight crossing
    if upper_seconds < lower_seconds:
        if current_seconds < lower_seconds:
            current_seconds += 24 * 3600
        upper_seconds += 24 * 3600
    
    # Perform linear interpolation
    total_diff = upper_seconds - lower_seconds
    if total_diff == 0:
        return lower_temp  # Avoid division by zero
    
    fraction = (current_seconds - lower_seconds) / total_diff
    interpolated_temp = lower_temp + fraction * (upper_temp - lower_temp)
    
    return int(round(interpolated_temp))

if __name__ == "__main__":
    try:
        lookup_table = load_lookup_table('lookup_table.csv')
        
        while True:
            current_time = datetime.now()
            cct = interpolate_color_temperature(lookup_table, current_time)
            converter = ColorTemperatureConverter(cct)
            converter.visualize_rgb_led()
            
            # Wait until the next 5-minute mark
            next_update = current_time + timedelta(minutes=5)
            next_update = next_update.replace(minute=next_update.minute // 5 * 5, second=0, microsecond=0)
            time.sleep((next_update - current_time).total_seconds())
    
    except KeyboardInterrupt:
        pass
    finally:
        red_led.off()
        green_led.off()
        blue_led.off()
