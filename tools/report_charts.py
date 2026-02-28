
import logging
import os
from typing import List, Dict
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ChartGenerator")

# Configure Plotting Style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_theme(style="whitegrid")

# Consistent Pastel Palette
PASTEL_COLORS = [
    '#AEC6CF', # Pastel Blue
    '#77DD77', # Pastel Green
    '#FF6961', # Pastel Red
    '#CB99C9', # Pastel Purple
    '#FFB347', # Pastel Orange
    '#FDFD96', # Pastel Yellow
    '#F49AC2', # Pastel Pink
    '#B0E0E6', # Powder Blue
    '#CFCFC4'  # Pastel Gray
]
PASTEL_OK = '#77DD77'
PASTEL_ERR = '#FF6961'

class ChartGenerator:
    def __init__(self, output_dir: str, scale: float = 1.0):
        self.output_dir = output_dir
        self.scale = scale
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_figsize(self, w, h):
        return (w * self.scale, h * self.scale)

    def save_plot(self, filename: str):
        path = os.path.join(self.output_dir, filename)
        # plt.tight_layout() # Creating warnings, bbox_inches='tight' in savefig handles this mostly
        try:
            plt.tight_layout()
        except Exception:
            pass # Ignore layout warnings
        plt.savefig(path, bbox_inches='tight', dpi=150)
        plt.close()
        return path

    def generate_pie_chart(self, data: pd.Series, title: str, filename: str, colors: Dict[str, str] = None):
        if data.empty:
            logger.warning(f"No data for pie chart: {title}")
            return None
        
        # Sanitize data: Drop NaNs and zeros
        data = data.fillna(0)
        data = data[data > 0]
        if data.empty:
            logger.warning(f"No positive data for pie chart: {title}")
            return None

        plt.figure(figsize=self._get_figsize(6, 4.5))
        color_list = None
        if colors:
            color_list = [colors.get(x, '#cccccc') for x in data.index]

        wedges, texts, autotexts = plt.pie(
            data, 
            labels=None, # No labels on pie
            autopct='%1.1f%%', 
            startangle=90, 
            colors=color_list,
            textprops=dict(color="black"),
            radius=0.9 # Smaller radius as requested (was 1.2)
        )
        
        # Determine label text color based on wedge color brightness could be nice, but black is safe for now.
        plt.setp(autotexts, size=7, weight="bold") # Smaller font
        plt.setp(texts, size=8)
        
        # Add Legend
        plt.legend(
            wedges, 
            data.index, 
            title=None, 
            loc="center left", 
            bbox_to_anchor=(1.1, 0, 0.5, 1), # Move legend slightly further right
            fontsize=7 # Smaller legend font
        )
        
        plt.title(title, fontsize=12, fontweight='bold')
        return self.save_plot(filename)

    def generate_bar_chart(self, df: pd.DataFrame, x_col: str, y_col: str, title: str, filename: str, color: str = None, figsize=None):
        if df.empty:
            return None
        
        # Sanitize
        df = df.copy()
        df[y_col] = df[y_col].fillna(0)
        
        # Use provided figsize or default (10, 6)
        base_size = figsize if figsize else (10, 6)
        plt.figure(figsize=self._get_figsize(*base_size))
        
        sns.barplot(data=df, x=x_col, y=y_col, color=color or "skyblue")
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(x_col, fontsize=12)
        plt.ylabel(y_col, fontsize=12)
        plt.xticks(rotation=45, ha='right')
        return self.save_plot(filename)

    def generate_horizontal_bar_chart(self, df: pd.DataFrame, x_col: str, y_col: str, title: str, filename: str, c_col: str = None, cmap: str = 'viridis', figsize=None):
        if df.empty: return None
        
        # Use provided figsize or default (10, len(df) * 0.5 + 2)
        base_size = figsize if figsize else (10, max(6, len(df) * 0.5 + 2))
        plt.figure(figsize=self._get_figsize(*base_size))
        
        # Color mapping if c_col is provided
        colors = None
        if c_col and c_col in df.columns:
            # Normalize c_col for color mapping
            norm = plt.Normalize(df[c_col].min(), df[c_col].max())
            try:
                import matplotlib
                cmap_obj = matplotlib.colormaps[cmap]
            except:
                cmap_obj = plt.cm.get_cmap(cmap)
            colors = cmap_obj(norm(df[c_col].values))
        
        bars = plt.barh(df[y_col], df[x_col], color=colors if colors is not None else PASTEL_COLORS[0], edgecolor='grey', alpha=0.9)
        
        plt.title(title, fontsize=12, fontweight='bold')
        plt.xlabel(x_col.replace('_', ' ').title(), fontsize=10)
        plt.yticks(fontsize=9)
        plt.xticks(fontsize=9)
        
        # Add value labels if space permits
        for i, bar in enumerate(bars):
            width = bar.get_width()
            label = f"{width:.2f}s"
            if c_col and c_col in df.columns:
                val = df.iloc[i][c_col]
                label += f" ({int(val)})"
            
            # Smart positioning: inside if bar is wide enough, outside otherwise
            # For now, simplistic approach: Outside
            plt.text(width, bar.get_y() + bar.get_height()/2, 
                     f' {label}', 
                     va='center', fontsize=8, color='black')
            
        plt.gca().invert_yaxis() # Top to bottom
        return self.save_plot(filename)

    def generate_stacked_bar_chart(self, df: pd.DataFrame, x_col: str, y_cols: List[str], title: str, filename: str, colors: List[str] = None, figsize=None):
        if df.empty: return None
        
        base_size = figsize if figsize else (10, 8)
        plt.figure(figsize=self._get_figsize(*base_size))
        
        # Plot bottom layer first, then add subsequent layers
        bottom = None
        
        # Use provided colors or default palette
        if not colors:
            colors = sns.color_palette("muted", len(y_cols))
            
        for i, col in enumerate(y_cols):
            plt.bar(
                df[x_col], 
                df[col], 
                bottom=bottom, 
                label=col, 
                color=colors[i] if i < len(colors) else None,
                edgecolor='black',
                alpha=0.8
            )
            if bottom is None:
                bottom = df[col]
            else:
                bottom += df[col]
                
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(x_col, fontsize=12)
        plt.ylabel("Latency (s)", fontsize=12)
        plt.xticks(rotation=45, ha='right')
        plt.legend()
        return self.save_plot(filename)


    def generate_xy_chart(self, df: pd.DataFrame, x_col: str, y_col: str, title: str, filename: str):
        if df.empty: return None
        plt.figure(figsize=(10, 6))
        sns.barplot(data=df, x=x_col, y=y_col, color="lightblue")
        plt.title(title)
        return self.save_plot(filename)

    def generate_scatter_plot(self, df: pd.DataFrame, x_col: str, y_col: str, hue_col: str, title: str, filename: str):
        if df.empty: return None
        plt.figure(figsize=(10, 6))
        sns.scatterplot(data=df, x=x_col, y=y_col, hue=hue_col, style=hue_col)
        plt.title(title)
        return self.save_plot(filename)

    def generate_histogram(self, df: pd.DataFrame, col: str, title: str, filename: str, bins=50, color='skyblue'):
        if df.empty: return None
        plt.figure(figsize=(10, 6))
        
        # Calculate statistics
        mean_val = df[col].mean()
        std_val = df[col].std()
        p95_val = df[col].quantile(0.95)
        
        plt.hist(df[col], bins=bins, alpha=0.7, color=color, edgecolor='black')
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(col.replace('_', ' ').title())
        plt.ylabel('Frequency')
        
        # Add summary lines
        plt.axvline(mean_val, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_val:.2f}')
        plt.axvline(p95_val, color='orange', linestyle='-.', linewidth=2, label=f'P95: {p95_val:.2f}')
        plt.legend()
        
        return self.save_plot(filename)

    def generate_stacked_bar(self, df: pd.DataFrame, x_col: str, y_col: str, hue_col: str, title: str, filename: str, figsize=None):
        """
        Custom stacked bar using seaborn/pandas logic.
        Useful for 'Latency by Category' type charts.
        """
        if df.empty: return None

        # Aggregate data for stacking
        pivot_df = df.groupby([x_col, hue_col]).size().unstack(fill_value=0)
        
        # Sort by Total Height (Descending)
        pivot_df['total'] = pivot_df.sum(axis=1)
        pivot_df = pivot_df.sort_values('total', ascending=False)
        pivot_df = pivot_df.drop(columns=['total'])
        
        base_size = figsize if figsize else (12, 6)
        plt.figure(figsize=self._get_figsize(*base_size))
        
        # Use pastel palette (cyclical if more categories than colors)
        color_cycle = PASTEL_COLORS * (len(pivot_df.columns) // len(PASTEL_COLORS) + 1)
        colors = color_cycle[:len(pivot_df.columns)]
        
        pivot_df.plot(kind='bar', stacked=True, figsize=self._get_figsize(*base_size), color=colors, edgecolor='grey', width=0.8, rot=45)
        
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(x_col.replace('_', ' ').title())
        plt.ylabel('Count')
        plt.xticks(rotation=45, ha='right')
        # Move legend outside if too many items
        plt.legend(title=hue_col.replace('_', ' ').title(), bbox_to_anchor=(1.02, 1), loc='upper left')
        
        return self.save_plot(filename)

    def generate_category_bar(self, df: pd.DataFrame, col: str, title: str, filename: str, order=None, colors=None, figsize=None):
        if df.empty: return None
        
        counts = df[col].value_counts()
        if order:
            counts = counts.reindex(order, fill_value=0)
            
        base_size = figsize if figsize else (10, 6)
        plt.figure(figsize=self._get_figsize(*base_size))
        
        bars = plt.bar(counts.index, counts.values, color=colors if colors else PASTEL_COLORS[0], edgecolor='grey')
        
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(col.replace('_', ' ').title())
        plt.ylabel('Count')
        plt.xticks(rotation=45, ha='right')
        
        # Add labels
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                plt.text(bar.get_x() + bar.get_width()/2., height,
                         f'{int(height)}', ha='center', va='bottom')
                 
        return self.save_plot(filename)

    def generate_scatter_with_trend(self, df: pd.DataFrame, x_col: str, y_col: str, c_col: str, title: str, filename: str, scale='linear'):
        if df.empty: return None
        
        plt.figure(figsize=(10, 8))
        
        # Filter positive values for log scale
        plot_df = df.copy()
        if scale == 'log':
            plot_df = plot_df[(plot_df[x_col] > 0) & (plot_df[y_col] > 0)]
            if plot_df.empty: return None
        
        scatter = plt.scatter(plot_df[x_col], plot_df[y_col], 
                             c=plot_df[c_col] if c_col else 'blue', 
                             cmap='viridis' if c_col else None, 
                             alpha=0.6, s=20, edgecolor='black', linewidth=0.1)
        
        if c_col:
            plt.colorbar(scatter, label=c_col.replace('_', ' ').title())
            
        if scale == 'log':
            plt.xscale('log')
            # plt.yscale('log') # Optional: log-log
            
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel(x_col.replace('_', ' ').title() + (' (Log Scale)' if scale == 'log' else ''))
        plt.ylabel(y_col.replace('_', ' ').title())
        plt.grid(True, alpha=0.3)
        
        # Add Trend Line (Polynomial fit)
        try:
            import numpy as np
            x = plot_df[x_col]
            y = plot_df[y_col]
            
            if scale == 'log':
                x = np.log10(x)
                # y = np.log10(y) # If log-log
            
            z = np.polyfit(x, y, 1)
            p = np.poly1d(z)
            
            x_trend = np.linspace(x.min(), x.max(), 100)
            y_trend = p(x_trend)
            
            if scale == 'log':
                x_plot = 10**x_trend
                y_plot = y_trend # 10**y_trend if log-log
            else:
                x_plot = x_trend
                y_plot = y_trend
                
            plt.plot(x_plot, y_plot, "r--", linewidth=2, alpha=0.8, label='Trend')
            plt.legend()
        except Exception as e:
            logger.warning(f"Could not add trend line: {e}")
            
        return self.save_plot(filename)

    def generate_sequence_plot(self, df: pd.DataFrame, y_col: str, title: str, filename: str):
        if df.empty: return None
        
        df = df.sort_values('timestamp').reset_index(drop=True)
        df['request_order'] = df.index + 1
        
        plt.figure(figsize=(12, 6))
        plt.scatter(df['request_order'], df[y_col], alpha=0.6, s=15, c=df[y_col], cmap='viridis')
        
        # Moving Average
        window = max(5, len(df) // 20)
        ma = df[y_col].rolling(window=window, center=True).mean()
        plt.plot(df['request_order'], ma, color='red', linewidth=2, alpha=0.8, label=f'{window}-pt Moving Avg')
        
        plt.title(title, fontsize=14, fontweight='bold')
        plt.xlabel('Request Order')
        plt.ylabel(y_col.replace('_', ' ').title())
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        return self.save_plot(filename)
