<?php
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class BNN_Intel_Admin {

	public static function init() {
		add_action( 'admin_menu', array( __CLASS__, 'menu' ) );
		add_action( 'admin_init', array( __CLASS__, 'register' ) );
		add_action( 'admin_post_bnn_intel_flush', array( __CLASS__, 'flush' ) );
	}

	public static function menu() {
		add_options_page( 'BNN Asia Intelligence', 'BNN Intelligence', 'manage_options', 'bnn-intel', array( __CLASS__, 'page' ) );
	}

	public static function register() {
		register_setting(
			'bnn_intel',
			'bnn_intel_settings',
			array(
				'sanitize_callback' => function ( $in ) {
					$old = BNN_Intel_API::settings();
					return array(
						'api_base'     => esc_url_raw( $in['api_base'] ?? $old['api_base'] ),
						// Keep the stored key when the field is left blank (it is never echoed back).
						'api_key'      => ! empty( $in['api_key'] ) ? sanitize_text_field( $in['api_key'] ) : $old['api_key'],
						'cache_ttl'    => max( 60, (int) ( $in['cache_ttl'] ?? 600 ) ),
						'country_base' => sanitize_title( $in['country_base'] ?? 'country-intelligence' ),
					);
				},
			)
		);
	}

	public static function flush() {
		check_admin_referer( 'bnn_intel_flush' );
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( 'Forbidden' );
		}
		BNN_Intel_API::flush_cache();
		flush_rewrite_rules();
		wp_safe_redirect( admin_url( 'options-general.php?page=bnn-intel&flushed=1' ) );
		exit;
	}

	public static function page() {
		$s      = BNN_Intel_API::settings();
		$health = BNN_Intel_API::get( 'config/' );
		?>
		<div class="wrap">
			<h1>BNN Asia Intelligence Connector</h1>
			<?php if ( isset( $_GET['flushed'] ) ) : ?><div class="notice notice-success"><p>Cache cleared.</p></div><?php endif; ?>
			<p><strong>API status:</strong>
				<?php
				if ( is_wp_error( $health ) ) {
					echo '<span style="color:#b32d2e">Not reachable – ' . esc_html( $health->get_error_message() ) . '</span>';
				} else {
					echo '<span style="color:#008a20">Connected</span> · period ' . esc_html( $health['period']['name'] ?? '?' ) . ' · ' . count( $health['categories'] ?? array() ) . ' public categories';
				}
				?>
			</p>
			<form method="post" action="options.php">
				<?php settings_fields( 'bnn_intel' ); ?>
				<table class="form-table">
					<tr><th>API base URL</th><td><input class="regular-text" name="bnn_intel_settings[api_base]" value="<?php echo esc_attr( $s['api_base'] ); ?>"></td></tr>
					<tr><th>API key</th><td><input class="regular-text" type="password" autocomplete="new-password" name="bnn_intel_settings[api_key]" placeholder="<?php echo $s['api_key'] ? '•••••••• (saved – leave blank to keep)' : 'bnn_…'; ?>"><p class="description">Issued in the research admin under API clients. Stored server-side only.</p></td></tr>
					<tr><th>Cache (seconds)</th><td><input type="number" min="60" name="bnn_intel_settings[cache_ttl]" value="<?php echo (int) $s['cache_ttl']; ?>"></td></tr>
					<tr><th>Country URL base</th><td>/<input name="bnn_intel_settings[country_base]" value="<?php echo esc_attr( $s['country_base'] ); ?>">/{country}/</td></tr>
				</table>
				<?php submit_button(); ?>
			</form>
			<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
				<input type="hidden" name="action" value="bnn_intel_flush"><?php wp_nonce_field( 'bnn_intel_flush' ); ?>
				<?php submit_button( 'Clear data cache & refresh URLs', 'secondary' ); ?>
			</form>
			<h2>Shortcodes</h2>
			<table class="widefat striped"><tbody>
				<tr><td><code>[bnn_intel_ranking]</code></td><td>BNN Asia Index table (search, region filter, sort). <code>category="press-freedom"</code> for one category.</td></tr>
				<tr><td><code>[bnn_intel_official indicator="wgi_cc"]</code></td><td>Published global ranking of a source organisation, with BNN-calculated Asia position clearly labelled.</td></tr>
				<tr><td><code>[bnn_intel_countries]</code></td><td>Country directory with search and region filter.</td></tr>
				<tr><td><code>[bnn_intel_country slug="bangladesh"]</code></td><td>Country profile (automatic on /<?php echo esc_html( $s['country_base'] ); ?>/{slug}/).</td></tr>
				<tr><td><code>[bnn_intel_category slug="good-governance"]</code></td><td>Category page: indicators and country values.</td></tr>
				<tr><td><code>[bnn_intel_compare]</code></td><td>Interactive country comparison.</td></tr>
				<tr><td><code>[bnn_intel_incidents country="bangladesh"]</code></td><td>Published, verified incidents.</td></tr>
				<tr><td><code>[bnn_intel_methodology]</code></td><td>Live methodology: weights, event taxonomy, data volume, limitations, open-data downloads.</td></tr>
			</tbody></table>
		</div>
		<?php
	}
}
