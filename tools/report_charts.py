import logging
import os
from typing import List, Dict
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import numpy as np

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ChartGenerator")

# Configure Professional Plotting Style
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({
    'font.size': 9,
    'axes.titlesize': 11,
    'axes.titleweight': 'bold',
    'axes.labelsize': 10,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'legend.title_fontsize': 10,
    'figure.titlesize': 12,
    'figure.titleweight': 'bold'
})

# Professional Palette
OK_COLOR = '#2ca02c' # Muted Green
ERR_COLOR = '#d62728' # Muted Red
NEUTRAL_COLOR = '#1f77b4' # Muted Blue

class ChartGenerator:
    def __init__(self, output_dir: str, scale: float = 1.0):
        self.output_dir = output_dir
        self.scale = scale
        os.makedirs(self.output_dir, exist_ok=True)
        # Standard Sizes (Width, Height)
        self.SIZE_PIE = (6.5, 4.5)
        self.SIZE_SMALL = (6, 4)
        self.SIZE_MEDIUM = (8, 6)
        self.SIZE_LARGE = (10, 8)

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

    def generate_pie_chart(self, data: pd.Series, title: str, filename: str, colors: Dict[str, str] = None, figsize=None):
        if data.empty:
            logger.warning(f"No data for pie chart: {title}")
            return None
        
        # Sanitize data: Drop NaNs and zeros
        data = data.fillna(0)
        data = data[data > 0]
        if data.empty:
            logger.warning(f"No positive data for pie chart: {title}")
            return None

        # Force a wider image size so pie chart PNGs don't clip long legends on the right
        base_size = (10.0, 4.5)
        fig = plt.figure(figsize=self._get_figsize(*base_size))
        
        # Absolute positioning: Pie chart strictly on the left half of the canvas
        ax = fig.add_axes([0.0, 0.1, 0.35, 0.75])
        
        color_list = None
        if colors:
             # Use provided color dict or fallback to seaborn palette
            color_list = [colors.get(x, sns.color_palette("muted")[i % len(sns.color_palette("muted"))]) for i, x in enumerate(data.index)]
            
        wedges, texts = ax.pie(
            data, 
            labels=None, # No labels on pie itself to avoid overlap
            startangle=90, 
            colors=color_list,
            wedgeprops=dict(width=0.4, edgecolor='w'), # Donut shape looks cleaner
            radius=1.0 # Force uniform radius
        )
        
        # Calculate percentages for the legend
        total = sum(data)
        legend_labels = [f"{idx} ({(val/total)*100:.1f}%)" for idx, val in zip(data.index, data)]

        # Calculate optimal number of columns for the legend (max ~12 items per column vertically)
        ncols = max(1, (len(data) // 13) + 1)

        # Add Legend to the right half of the canvas
        ax_legend = fig.add_axes([0.35, 0.1, 0.65, 0.75])
        ax_legend.axis('off')
        ax_legend.legend(
            wedges, 
            legend_labels, 
            title=None, 
            loc="center left", 
            fontsize=9,
            ncol=ncols
        )
        
        # Absolute title positioning
        fig.text(0.0, 0.95, title, fontsize=9, fontweight='bold', ha='left', va='top')
        
        # Save explicitly bypassing tight_layout so the canvas bounds are identical for all charts
        path = os.path.join(self.output_dir, filename)
        plt.savefig(path, dpi=150)
        plt.close(fig)
        return path

    def generate_bar_chart(self, df: pd.DataFrame, x_col: str, y_col: str, title: str, filename: str, color: str = None, figsize=None):
        if df.empty:
            return None
        
        # Sanitize
        df = df.copy()
        df[y_col] = df[y_col].fillna(0)
        
        base_size = figsize if figsize else self.SIZE_MEDIUM
        plt.figure(figsize=self._get_figsize(*base_size))
        
        sns.barplot(data=df, x=x_col, y=y_col, color=color or NEUTRAL_COLOR)
        plt.title(title, pad=15)
        plt.xlabel(x_col.replace('_', ' ').title())
        plt.ylabel(y_col.replace('_', ' ').title())
        plt.xticks(rotation=45, ha='right')
        return self.save_plot(filename)

    def generate_horizontal_bar_chart(self, df: pd.DataFrame, x_col: str, y_col: str, title: str, filename: str, c_col: str = None, cmap: str = 'Blues', figsize=None):
        if df.empty: return None
        
        # Calculate dynamic height based on number of bars, but cap it so it doesn't get ridiculously tall
        calculated_height = max(self.SIZE_MEDIUM[1], len(df) * 0.4 + 1)
        base_size = figsize if figsize else (self.SIZE_MEDIUM[0], calculated_height)
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
        
        bars = plt.barh(df[y_col], df[x_col], color=colors if colors is not None else NEUTRAL_COLOR, edgecolor='none', alpha=0.9)
        
        plt.title(title, pad=15)
        plt.xlabel(x_col.replace('_', ' ').title())
        
        # Add value labels
        for i, bar in enumerate(bars):
            width = bar.get_width()
            label = f"{width:.2f}"
            if "ms" in x_col.lower() or "latency" in x_col.lower() or "(s)" in x_col:
                 label += "s"
            if c_col and c_col in df.columns:
                val = df.iloc[i][c_col]
                label += f" (n={int(val)})"
            
            # Smart positioning: inside if bar is wide enough, outside otherwise
            plt.text(width + str(width).count('.')*0.01, bar.get_y() + bar.get_height()/2, 
                     f' {label}', 
                     va='center', fontsize=9, color='black')
            
        plt.gca().invert_yaxis() # Top to bottom
        sns.despine(left=True, bottom=True) # Cleaner look for horizontal bars
        return self.save_plot(filename)

    def generate_stacked_bar_chart(self, df: pd.DataFrame, x_col: str, y_cols: List[str], title: str, filename: str, colors: List[str] = None, figsize=None):
        if df.empty: return None
        
        base_size = figsize if figsize else self.SIZE_LARGE
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
                edgecolor='white',
                linewidth=0.5,
                alpha=0.9
            )
            if bottom is None:
                bottom = df[col]
            else:
                bottom += df[col]
                
        plt.title(title, pad=15)
        plt.xlabel(x_col.replace('_', ' ').title())
        plt.ylabel("Latency (s)")
        plt.xticks(rotation=45, ha='right')
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        sns.despine()
        return self.save_plot(filename)


    def generate_xy_chart(self, df: pd.DataFrame, x_col: str, y_col: str, title: str, filename: str):
        if df.empty: return None
        plt.figure(figsize=self._get_figsize(*self.SIZE_MEDIUM))
        sns.barplot(data=df, x=x_col, y=y_col, color=NEUTRAL_COLOR)
        plt.title(title, pad=15)
        sns.despine()
        return self.save_plot(filename)

    def generate_scatter_plot(self, df: pd.DataFrame, x_col: str, y_col: str, hue_col: str, title: str, filename: str):
        if df.empty: return None
        plt.figure(figsize=self._get_figsize(*self.SIZE_MEDIUM))
        sns.scatterplot(data=df, x=x_col, y=y_col, hue=hue_col, style=hue_col, s=80)
        plt.title(title, pad=15)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        sns.despine()
        return self.save_plot(filename)

    def generate_histogram(self, df: pd.DataFrame, col: str, title: str, filename: str, bins=50, color=NEUTRAL_COLOR):
        if df.empty: return None
        plt.figure(figsize=self._get_figsize(*self.SIZE_MEDIUM))
        
        # Calculate statistics
        mean_val = df[col].mean()
        std_val = df[col].std()
        p95_val = df[col].quantile(0.95)
        
        plt.hist(df[col], bins=bins, alpha=0.8, color=color, edgecolor='white')
        plt.title(title, pad=15)
        plt.xlabel(col.replace('_', ' ').title())
        plt.ylabel('Frequency')
        
        # Add summary lines
        plt.axvline(mean_val, color=ERR_COLOR, linestyle='--', linewidth=2, label=f'Mean: {mean_val:.2f}')
        plt.axvline(p95_val, color='#ff7f0e', linestyle='-.', linewidth=2, label=f'P95: {p95_val:.2f}')
        plt.legend()
        sns.despine()
        
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
        
        base_size = figsize if figsize else self.SIZE_LARGE
        plt.figure(figsize=self._get_figsize(*base_size))
        
        colors = sns.color_palette("muted", len(pivot_df.columns))
        
        pivot_df.plot(kind='bar', stacked=True, figsize=self._get_figsize(*base_size), color=colors, edgecolor='white', width=0.8, rot=45)
        
        plt.title(title, pad=15)
        plt.xlabel(x_col.replace('_', ' ').title())
        plt.ylabel('Count')
        plt.xticks(rotation=45, ha='right')
        # Move legend outside if too many items
        plt.legend(title=hue_col.replace('_', ' ').title(), bbox_to_anchor=(1.05, 1), loc='upper left')
        sns.despine()
        
        return self.save_plot(filename)

    def generate_category_bar(self, df: pd.DataFrame, col: str, title: str, filename: str, order=None, colors=None, figsize=None):
        if df.empty: return None
        
        counts = df[col].value_counts()
        if order:
            counts = counts.reindex(order, fill_value=0)
            
        base_size = figsize if figsize else self.SIZE_MEDIUM
        plt.figure(figsize=self._get_figsize(*base_size))
        
        bars = plt.bar(counts.index, counts.values, color=colors if colors else NEUTRAL_COLOR, edgecolor='white')
        
        plt.title(title, pad=15)
        plt.xlabel(col.replace('_', ' ').title())
        plt.ylabel('Count')
        plt.xticks(rotation=45, ha='right')
        
        # Add labels
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                plt.text(bar.get_x() + bar.get_width()/2., height,
                         f'{int(height)}', ha='center', va='bottom', fontsize=9)
        sns.despine()         
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
