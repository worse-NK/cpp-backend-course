#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>

// A deliberately small, classic histogram for one measured operation.
// The mutex makes each exported snapshot internally consistent.
class Metrics {
    mutable std::mutex mutex_;
    std::uint64_t active_ = 0, ok_ = 0, error_ = 0, good_ = 0;
    std::array<std::uint64_t, 3> buckets_{};
    double sum_ = 0;
public:
    void enter() { std::lock_guard lock(mutex_); ++active_; }
    void complete(double seconds, bool success) {
        if (!std::isfinite(seconds) || seconds < 0)
            throw std::invalid_argument("duration must be finite and nonnegative");
        std::lock_guard lock(mutex_);
        if (active_ == 0) throw std::logic_error("no matching enter");
        --active_;
        success ? ++ok_ : ++error_;
        if (success && seconds <= 0.3) ++good_;
        constexpr std::array bounds{0.1, 0.3, 1.0};
        for (std::size_t i = 0; i != bounds.size(); ++i)
            if (seconds <= bounds[i]) ++buckets_[i];
        sum_ += seconds;
    }
    std::string exposition() const {
        std::lock_guard lock(mutex_);
        std::ostringstream out;
        out << std::fixed << std::setprecision(6);
        out << "# TYPE course_requests_total counter\n"
            << "course_requests_total{outcome=\"ok\"} " << ok_ << '\n'
            << "course_requests_total{outcome=\"error\"} " << error_ << '\n'
            << "# TYPE course_good_requests_total counter\n"
            << "course_good_requests_total " << good_ << '\n'
            << "# TYPE course_inflight gauge\ncourse_inflight " << active_ << '\n'
            << "# TYPE course_request_duration_seconds histogram\n";
        constexpr std::array names{"0.1", "0.3", "1"};
        for (std::size_t i = 0; i != names.size(); ++i)
            out << "course_request_duration_seconds_bucket{le=\"" << names[i]
                << "\"} " << buckets_[i] << '\n';
        out << "course_request_duration_seconds_bucket{le=\"+Inf\"} "
            << ok_ + error_ << '\n'
            << "course_request_duration_seconds_sum " << sum_ << '\n'
            << "course_request_duration_seconds_count " << ok_ + error_ << '\n';
        return out.str();
    }
};
